"""
Connettore Banca Valsabbina – Estratto conto corrente ordinario.
Layout: DATA(GG/MM) | VALUTA(GG/MM/AA) | DARE | AVERE | DESCRIZIONE
"""
import re
from datetime import datetime
from collections import defaultdict


def get_id():
    return "valsabbina"


def get_name():
    return "Banca Valsabbina"


def get_doc_prefix():
    return "VLB"


def _parse_amount(s):
    s = str(s).strip().replace('\xa0', '').replace(' ', '')
    s = re.sub(r'^[+\-]', '', s).strip()
    try:
        return float(s.replace('.', '').replace(',', '.'))
    except Exception:
        return None


def _parse_date_op(s, year):
    """Converte GG/MM (con anno da contesto) in YYYY-MM-DD."""
    m = re.match(r'^(\d{2})/(\d{2})$', s.strip())
    if not m:
        return None
    day, month = int(m.group(1)), int(m.group(2))
    y = year - 1 if (month == 12 and year % 100 == 1) else year
    try:
        return datetime(y, month, day).strftime('%Y-%m-%d')
    except Exception:
        return None


DATE_OP_RE  = re.compile(r'^\d{2}/\d{2}$')
DATE_VAL_RE = re.compile(r'^\d{2}/\d{2}/\d{2,4}$')
AMOUNT_RE   = re.compile(r'^\d{1,3}(?:\.\d{3})*,\d{2}$')
NOP_RE      = re.compile(r'\(?NOP\s+[^\)]+\)?[EG]?', re.IGNORECASE)
TABLE_END_RE = re.compile(r'SALDO FINALE', re.IGNORECASE)

SKIP_PATTERNS = [re.compile(p, re.IGNORECASE) for p in [
    r'^DATA\s+VALUTA',
    r'^Estratto conto corrente',
    r'^DEL CONTO IN EURO',
    r'^N\.: \d+',
    r'^COMUNICAZIONE N\.',
    r'^EL\d+',
    r'^Ci pregiamo', r'^bancaria', r'^approvati', r'^presso il quale',
    r'^Distinti saluti', r'^Imposta bollo virtuale',
    r'^Il presente rapporto', r'^prendere visione', r'^sul sito della banca',
    r"^L'eventuale presenza", r"^'G' indica", r'^puntuale con',
    r'^VESTONE,', r'^BANCA VALSABBINA',
    r'^Costruisci valore', r'^Con il Piano', r'^obiettivi futuri',
    r'^Messaggio pubblicitario',
    r'^\d{5}\s',
]]


def _should_skip(text):
    t = text.strip()
    if not t:
        return True
    for p in SKIP_PATTERNS:
        if p.match(t):
            return True
    return False


def _clean_desc(d):
    """Rimuove codici NOP e spazi multipli."""
    d = NOP_RE.sub('', d)
    return re.sub(r'\s+', ' ', d).strip()


def _is_continuation_junk(text):
    """
    Righe di continuazione da ignorare: solo date/codici tecnici
    senza testo descrittivo utile, oppure solo NOP.
    """
    t = _clean_desc(text)
    # Se dopo pulizia NOP rimane solo roba tecnica (IBAN, CRO, date, ecc.)
    # la teniamo comunque — l'utente può vedere i dettagli
    # Scartiamo solo se è vuoto dopo pulizia
    return len(t) == 0


def extract(pdf_source):
    import pdfplumber

    saldo_iniziale = saldo_finale = None
    transactions = []

    with pdfplumber.open(pdf_source) as pdf:
        # Anno e saldo iniziale dalla prima pagina
        p1_text = pdf.pages[0].extract_text() or ''
        year = datetime.today().year
        m = re.search(r'al\s+\d{2}/\d{2}/(\d{4})', p1_text)
        if m:
            year = int(m.group(1))

        m_si = re.search(r'([\d\.]+,\d{2})\s+SALDO COME DA COMUNICAZIONE', p1_text)
        if m_si:
            saldo_iniziale = _parse_amount(m_si.group(1))

        for page in pdf.pages:
            words = page.extract_words(
                keep_blank_chars=False, x_tolerance=3, y_tolerance=3
            )
            if not words:
                continue

            rows_dict = defaultdict(list)
            for w in words:
                rows_dict[round(w['top'] / 4) * 4].append(w)
            sorted_rows = sorted(rows_dict.items())

            # Calibra colonne dall'header
            table_start_top = None
            dare_x = 162.0
            avere_x = 224.0
            desc_x = 255.0

            for top, rw in sorted_rows:
                row_txt = ' '.join(w['text'] for w in sorted(rw, key=lambda x: x['x0']))
                if 'DATA' in row_txt and 'VALUTA' in row_txt and 'DARE' in row_txt:
                    table_start_top = top
                    for w in rw:
                        if w['text'] == 'DARE':        dare_x  = (w['x0'] + w['x1']) / 2
                        if w['text'] == 'AVERE':       avere_x = (w['x0'] + w['x1']) / 2
                        if w['text'] == 'DESCRIZIONE': desc_x  = w['x0']
                    break

            if table_start_top is None:
                continue

            mid_da = (dare_x + avere_x) / 2
            current_tx = None

            for top, rw in sorted_rows:
                if top <= table_start_top:
                    continue

                sorted_w = sorted(rw, key=lambda x: x['x0'])
                row_txt  = ' '.join(w['text'] for w in sorted_w)

                # Saldo finale
                if TABLE_END_RE.search(row_txt):
                    m_sf = re.search(r'([\d\.]+,\d{2})', row_txt)
                    if m_sf:
                        saldo_finale = _parse_amount(m_sf.group(1))
                    if current_tx:
                        transactions.append(current_tx)
                        current_tx = None
                    break

                if _should_skip(row_txt):
                    continue

                # Data operazione (prima parola, x<55, formato GG/MM)
                first_w = sorted_w[0] if sorted_w else None
                data_op = None
                if first_w and DATE_OP_RE.match(first_w['text']) and first_w['x0'] < 55:
                    data_op = _parse_date_op(first_w['text'], year)

                # Importi DARE / AVERE
                dare_val = avere_val = dare_word = avere_word = None
                for w in sorted_w:
                    cx = (w['x0'] + w['x1']) / 2
                    if AMOUNT_RE.match(w['text']) and cx < desc_x - 5:
                        if cx <= mid_da:
                            dare_val  = _parse_amount(w['text']); dare_word  = w
                        else:
                            avere_val = _parse_amount(w['text']); avere_word = w

                # Descrizione: parole nella zona desc
                desc_words = []
                for w in sorted_w:
                    if w is dare_word or w is avere_word:
                        continue
                    if w['x0'] < 55 and DATE_OP_RE.match(w['text']):
                        continue
                    if w['x0'] < 120 and DATE_VAL_RE.match(w['text']):
                        continue
                    if w['x0'] >= desc_x - 1:
                        desc_words.append(w['text'])

                desc_raw = ' '.join(desc_words).strip()
                desc = _clean_desc(desc_raw)

                # Nuova transazione
                if data_op and (dare_val is not None or avere_val is not None):
                    if current_tx:
                        transactions.append(current_tx)
                    current_tx = {
                        'data_op':     data_op,
                        'uscita':      dare_val,
                        'entrata':     avere_val,
                        'descrizione': desc[:255],
                        'causale':     '',
                        'conto_dare':  '',
                        'conto_avere': '',
                        'numero_doc':  '',
                    }

                # Riga di continuazione
                elif not data_op and current_tx:
                    # Prendi solo le parole nella zona descrizione
                    cont_words = [
                        w['text'] for w in sorted_w
                        if w['x0'] >= desc_x - 1
                    ]
                    # Pulisci e rimuovi NOP
                    cont = _clean_desc(' '.join(cont_words))
                    # Scarta se dopo pulizia rimane solo una data o codice alfanum puro
                    cont = re.sub(r'^\d{2}/\d{2}/\d{2,4}\s*', '', cont).strip()
                    cont = re.sub(r'^[A-Z0-9]{8,}\)G?\s*$', '', cont).strip()
                    if cont:
                        current_tx['descrizione'] = (
                            current_tx['descrizione'] + ' ' + cont
                        ).strip()[:255]

            if current_tx:
                transactions.append(current_tx)

    # Post-processing
    transactions = [
        tx for tx in transactions
        if (tx.get('uscita') or tx.get('entrata')) and tx.get('descrizione')
    ]

    # Pulizia finale descrizioni
    for tx in transactions:
        tx['descrizione'] = _clean_desc(tx['descrizione'])[:255]

    # Deduplicazione
    seen = set()
    final = []
    for tx in transactions:
        key = (tx['data_op'], tx['uscita'], tx['entrata'], tx['descrizione'])
        if key not in seen:
            seen.add(key)
            final.append(tx)

    return final, saldo_iniziale, saldo_finale
