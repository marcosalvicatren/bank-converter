"""
Connettore American Express – Estratto conto Carta Oro Business (e simili).
Tutte le operazioni sono uscite (addebiti sulla carta),
tranne "ADDEBITO IN C/C SALVO BUON FINE" che e' un accredito (pagamento ricevuto).
"""
import re
from datetime import datetime
from collections import defaultdict


def get_id():
    return "amex"


def get_name():
    return "American Express (Carta Oro / Business)"


def get_doc_prefix():
    return "AMEX"


def _parse_amount(s):
    s = str(s).strip().replace('\xa0', '').replace(' ', '')
    s = re.sub(r'^[+\-]', '', s).strip()
    try:
        return float(s.replace('.', '').replace(',', '.'))
    except Exception:
        return None


def _parse_date(s):
    s = s.strip()
    for fmt in ('%d.%m.%y', '%d.%m.%Y'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    return None


DATE_RE   = re.compile(r'^\d{2}\.\d{2}\.\d{2}$')
AMOUNT_RE = re.compile(r'^\d{1,3}(?:\.\d{3})*,\d{2}$')

TABLE_END_PATTERNS = [re.compile(p, re.IGNORECASE) for p in [
    r'^Totale nuove operazioni',
    r'^Totale interessi',
    r'^Modalita di Pagamento',
    r'^Modalità di Pagamento',
    r'^Tasso di cambio$',
    r'^Modalita di rimborso',
    r'^Per eventuali chiarimenti',
    r'^American Express Italia',
    r'^AVVISO DI PAGAMENTO',
    r'^Membership Rewards',
    r'^\.\.',
    r'^Nuovi Punti',
    r'^Punti Bonus',
    r'^I Nuovi Punti',
    r'^SBS Oro',
]]

SKIP_IN_TABLE = [re.compile(p, re.IGNORECASE) for p in [
    r'^Tasso di Cambio\s+\d',
    r'^ARRIVO\s+PARTENZA',
    r'^\d{2}/\d{2}/\d{2,4}\s+\d{2}/\d{2}/\d{2,4}',
    r'^\d{2}/\d{2}/\d{2,4}$',
    r'^\d{1,2}$',
    r'^Carta xxxx',
    r'^Pagina \d+',
    r'^Titolare',
    r'^Data\s+operazione',
    r'^Data\s+Contabilizzata',
    r'^operazione\s+data',
    r'^Ristoranti$',
    r'^Alberghi$',
    r'^INTERESSI, ALTRI ADDEBITI',
    r'^Nuovi addebiti per ',
    r'^SIG .* Totale',
    r'^SIG RIMON',
    r'^GRAYBRIDGE',
    r'^Nuovi addebiti per',
    r'^TOTALE ALTRI ADDEBITI',
    r'^Carta Oro Business',
    r'^Estratto Conto$',
    r'^americanexpress',
    r'^VIA ',
    r'^\d{5} ',
    r'^ITALY$',
    r'^Pesos Argentini$',
    r'^Dollari Statunitensi$',
    r'^Quetzal del Guatemala$',
    r'^Zloty Polacchi$',
    r'^CR$',
]]

VALUTA_WORDS = {
    'Pesos', 'Argentini', 'Dollari', 'Statunitensi',
    'Quetzal', 'Guatemala', 'del', 'Polacchi', 'Zloty', 'CR',
}

LEGAL_STARTS = (
    'nel caso', 'qualora', 'per eventuali', 'eventuali addebiti',
    'modalità', "l'importo", 'ti informiamo', 'in caso',
    'necessità', 'servizio clienti', 'american express',
    'puoi aggiornare', 'del sito', 'contattando',
    'sito internet', 'soggetto', 'iscritta', 'imposta',
)


def _is_table_end(text):
    for p in TABLE_END_PATTERNS:
        if p.match(text.strip()):
            return True
    return False


def _skip_in_table(text):
    t = text.strip()
    if not t:
        return True
    for p in SKIP_IN_TABLE:
        if p.match(t):
            return True
    return False


def extract(pdf_source):
    import pdfplumber

    saldo_iniziale = saldo_finale = None
    transactions = []

    open_ctx = pdfplumber.open(pdf_source)
    with open_ctx as pdf:
        # Saldi da pagina 1
        p1 = pdf.pages[0].extract_text() or ''
        m = re.search(
            r'([\d\.]+,\d{2})\s*[-]\s*([\d\.]+,\d{2})\s*[+]\s*([\d\.]+,\d{2})\s*=\s*([\d\.]+,\d{2})',
            p1
        )
        if m:
            saldo_iniziale = _parse_amount(m.group(1))
            saldo_finale   = _parse_amount(m.group(4))

        for page in pdf.pages:
            words = page.extract_words(keep_blank_chars=False, x_tolerance=3, y_tolerance=3)
            if not words:
                continue

            rows_dict = defaultdict(list)
            for w in words:
                rows_dict[round(w['top'] / 4) * 4].append(w)
            sorted_rows = sorted(rows_dict.items())

            # Trova zona tabella e colonna importo
            table_start_top = table_end_top = importo_col_x = None

            for top, rw in sorted_rows:
                row_txt = ' '.join(w['text'] for w in sorted(rw, key=lambda x: x['x0']))
                if table_start_top is None and 'operazione' in row_txt and 'data' in row_txt.lower():
                    table_start_top = top
                    for w in rw:
                        if w['text'] == 'Euro':
                            importo_col_x = w['x0'] - 15
                            break
                if table_start_top is not None and table_end_top is None:
                    if _is_table_end(row_txt):
                        table_end_top = top

            if table_start_top is None:
                continue
            if importo_col_x is None:
                importo_col_x = 460

            table_rows = [
                (top, rw) for top, rw in sorted_rows
                if top > table_start_top and (table_end_top is None or top < table_end_top)
            ]

            current_tx = None

            for top, rw in table_rows:
                sorted_w = sorted(rw, key=lambda x: x['x0'])
                row_txt  = ' '.join(w['text'] for w in sorted_w)

                if _skip_in_table(row_txt):
                    continue

                # Date a sinistra
                date_candidates = [
                    w['text'] for w in sorted_w
                    if w['x0'] < 120 and DATE_RE.match(w['text'])
                ]
                data_op = _parse_date(date_candidates[0]) if date_candidates else None

                # Importo Euro
                importo = importo_word = None
                for w in reversed(sorted_w):
                    if (w['x0'] + w['x1']) / 2 > importo_col_x and AMOUNT_RE.match(w['text']):
                        importo = _parse_amount(w['text'])
                        importo_word = w
                        break

                # CR marker
                is_credit_row = any(w['text'] == 'CR' for w in sorted_w)

                # Descrizione: zona centrale
                desc_words = []
                for w in sorted_w:
                    if w['x0'] < 120 and DATE_RE.match(w['text']):
                        continue
                    if w is importo_word:
                        continue
                    cx = (w['x0'] + w['x1']) / 2
                    if cx > importo_col_x - 100 and AMOUNT_RE.match(w['text']):
                        continue
                    if cx > importo_col_x - 130 and w['text'] in VALUTA_WORDS:
                        continue
                    desc_words.append(w['text'])

                desc = re.sub(r'\s+', ' ', ' '.join(desc_words)).strip()

                # Riga CR isolata (senza data/importo/descrizione)
                if is_credit_row and not data_op and not importo and not desc:
                    if current_tx:
                        current_tx['entrata'] = current_tx['uscita']
                        current_tx['uscita']  = None
                    continue

                # Nuova transazione
                if data_op and importo:
                    if current_tx:
                        transactions.append(current_tx)

                    is_payment = 'ADDEBITO IN C/C' in desc.upper()
                    if is_payment or is_credit_row:
                        uscita = None; entrata = importo
                    else:
                        uscita = importo; entrata = None

                    current_tx = {
                        'data_op':     data_op,
                        'uscita':      uscita,
                        'entrata':     entrata,
                        'descrizione': desc[:255],
                        'causale':     '',
                        'conto_dare':  '',
                        'conto_avere': '',
                        'numero_doc':  '',
                    }

                # Riga di continuazione
                elif not data_op and desc and current_tx:
                    if not any(desc.lower().startswith(s) for s in LEGAL_STARTS):
                        current_tx['descrizione'] = (
                            current_tx['descrizione'] + ' ' + desc
                        ).strip()[:255]

            if current_tx:
                transactions.append(current_tx)

    # Post-processing
    transactions = [
        tx for tx in transactions
        if (tx.get('uscita') or tx.get('entrata')) and tx.get('descrizione')
    ]

    for tx in transactions:
        d = re.sub(r'(\s+\d{1,3}(?:[,\.]\d{3})*(?:[,\.]\d{2})?)+\s*$', '', tx['descrizione'])
        tx['descrizione'] = re.sub(r'\s+', ' ', d).strip()[:255]

    seen = set()
    final = []
    for tx in transactions:
        key = (tx['data_op'], tx['uscita'], tx['entrata'], tx['descrizione'])
        if key not in seen:
            seen.add(key)
            final.append(tx)

    return final, saldo_iniziale, saldo_finale
