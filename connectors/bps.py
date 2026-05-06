"""
Connettore Banca Popolare di Sondrio (BPS) – Estratto conto cartaceo.
Gruppo BPER Banca. Sarà aggiornato a Biper Banca quando cambia il formato.
"""
import re, io
from datetime import datetime
from collections import defaultdict

def get_id():
    return "bps"

def get_name():
    return "Banca Popolare di Sondrio (BPS / BPER)"

def get_doc_prefix():
    return "BPS"

# ─── helpers ──────────────────────────────────────────────────────────────────
def _parse_amount(s):
    s = s.strip().replace('€','').replace('\xa0','').replace(' ','')
    s = re.sub(r'^[+\-−]', '', s).strip()
    try:
        return float(s.replace('.','').replace(',','.'))
    except:
        return None

# ─── extractor ────────────────────────────────────────────────────────────────
def extract(pdf_source):
    """
    Accetta path stringa o file-like object (upload Streamlit).
    Ritorna (transactions, saldo_iniziale, saldo_finale).
    """
    import pdfplumber

    DATE_RE   = re.compile(r'^\d{2}/\d{2}/\d{4}$')
    AMOUNT_RE = re.compile(r'^\d{1,3}(?:\.\d{3})*,\d{2}$')

    # Parole da ignorare nelle righe di continuazione
    SKIP_KW = set([
        'Data','Valuta','Movimenti','Dare','Avere','Descrizione','operazione',
        'Saldo','iniziale','finale','Totale','movimenti','Giacenza','media','annua',
        'BBAN','IBAN','BIC','SWIFT','Nazionali','Internazionali','Bank','Indentifier',
        'Code','Pagina','Estratto','Conto','Documento','numero','di',
        'Situazione','al','Corrente','n.','EUR','Filiale','LUMEZZANE',
        'LIRFO001','POSOIT22',
        'Banca','Popolare','Sondrio','Gruppo','BPER',
        'IMPOSTA','BOLLO','ASSOLTA','MODO','VIRTUALE','AUT',
        'rammenta','sensi','comma','Norme','contrattuali','regolano',
        'rapporto','conto','corrente','corrispondenza','estratti',
        'intenderanno','approvati','correntista','pieno','effetto',
        'riguardo','elementi','concorso','formare','risultanze',
        'laddove','trascorsi','giorni','data','ricevimento','tali',
        'etratti','medesimo','abbia','fatto','pervenire',
        "all'Azienda",'credito','per','iscritto','reclamo','specifico',
        'Si','BANCA','POPOLARE','DI','SONDRIO','Sede','Centrale',
        'Società','azioni','Fondata','nel','1871','Iscritta','Registro',
        'Imprese','Codice','Fiscale','Partita','IVA','Albo','Banche',
        'Aderente','Fondo','Interbancario','Tutela','Depositi',
        'appartenente','bancario','iscritto','Gruppi','bancari',
        'soggetta','attività','direzione','coordinamento',
        'messaggio','protegge','riservatezza','Suoi','dati','personali',
        'poiché','impedisce','lettura','trasparenza',
    ])

    # Testi che indicano header/footer da saltare completamente
    HEADER_KW = [
        'Data Valuta Movimenti','Saldo iniziale','Saldo finale','Totale movimenti',
        'Giacenza media','BBAN','IBAN','Pagina','Situazione al','Conto Corrente',
        'Filiale di','LIRFO001','POSOIT22','Banca Popolare','BPER',
        'IMPOSTA DI BOLLO ASSOLTA','Si rammenta','BANCA POPOLARE DI SONDRIO',
        'Fondata nel','Codice Fiscale','Partita IVA',
        'SPORTELLO','INTERNAZIONALIZZAZIONE','Documento numero',
        'messaggio protegge','trasparenza',
    ]

    saldo_iniziale = saldo_finale = None
    transactions = []

    open_ctx = pdfplumber.open(pdf_source) if isinstance(pdf_source, str) else pdfplumber.open(pdf_source)

    with open_ctx as pdf:
        for page in pdf.pages:
            words = page.extract_words(keep_blank_chars=False, x_tolerance=3, y_tolerance=3)
            if not words:
                continue
            full_text = page.extract_text() or ''

            # Saldo iniziale / finale
            for line in full_text.split('\n'):
                ls = line.strip()
                m = re.match(r'(\d{2}/\d{2}/\d{4})\s+([\d\.]+,\d{2})\s+Saldo iniziale', ls)
                if m and saldo_iniziale is None:
                    saldo_iniziale = _parse_amount(m.group(2))
                m2 = re.match(r'(\d{2}/\d{2}/\d{4})\s+([\d\.]+,\d{2})\s+Saldo finale', ls)
                if m2:
                    saldo_finale = _parse_amount(m2.group(2))

            # Calibrazione colonne dalla riga intestazione
            # Layout BPS: Data(~23) Valuta(~79) Dare(~180-200) Avere(~270-300) Desc(~343+)
            dare_x_center = avere_x_center = None
            for w in words:
                if w['text'] == 'Dare'  and w['top'] < 400: dare_x_center  = (w['x0']+w['x1'])/2
                if w['text'] == 'Avere' and w['top'] < 400: avere_x_center = (w['x0']+w['x1'])/2
            if dare_x_center  is None: dare_x_center  = 220
            if avere_x_center is None: avere_x_center = 310

            mid_da = (dare_x_center + avere_x_center) / 2

            # desc_x_start: le descrizioni iniziano DOPO la colonna Avere.
            # Dal PDF misuriamo x≈343. Usiamo avere_x + 30 (più permissivo).
            desc_x_start = avere_x_center + 20

            # Soglia X massima per le colonne numeriche:
            # un importo oltre desc_x_start è testo della descrizione, non un importo
            amt_x_max = avere_x_center + 15

            # Raggruppa per riga
            rows_dict = defaultdict(list)
            for w in words:
                rows_dict[round(w['top'] / 4) * 4].append(w)
            sorted_rows = sorted(rows_dict.items())

            def row_text_full(rw):
                return ' '.join(w['text'] for w in sorted(rw, key=lambda x: x['x0']))

            def is_header_or_skip(rw):
                txt = row_text_full(rw)
                return any(k in txt for k in HEADER_KW)

            def split_row(rw):
                """
                Divide la riga in: data_val, dare_words, avere_words, desc_text
                
                Regola chiave: una data è "data operazione" solo se la sua
                posizione X è nella zona colonna Data (<= 120).
                Date con x > 120 fanno parte della descrizione.
                """
                sorted_w = sorted(rw, key=lambda x: x['x0'])
                dare_words  = []
                avere_words = []
                desc_words  = []
                data_val    = None

                for w in sorted_w:
                    cx = (w['x0'] + w['x1']) / 2
                    t  = w['text']

                    if DATE_RE.match(t):
                        if w['x0'] <= 120:
                            # È una data di operazione o valuta (prima o seconda colonna)
                            if data_val is None:
                                data_val = t   # prima data = data operazione
                            # seconda data = valuta, ignorata
                        else:
                            # Data dentro la descrizione (es. "dal 01/10/2025 al 31/12/2025")
                            desc_words.append(t)
                    elif AMOUNT_RE.match(t) and cx <= amt_x_max:
                        # Importo nelle colonne dare/avere
                        if cx < mid_da:
                            dare_words.append(t)
                        else:
                            avere_words.append(t)
                    elif cx >= desc_x_start:
                        # Testo descrizione
                        desc_words.append(t)

                return data_val, dare_words, avere_words, ' '.join(desc_words)

            current_tx = None
            for top, rw in sorted_rows:
                if is_header_or_skip(rw):
                    continue
                txt_full = row_text_full(rw)
                if not txt_full.strip():
                    continue

                data_val, dare_ws, avere_ws, desc_inline = split_row(rw)

                if data_val:
                    # Salva transazione precedente
                    if current_tx:
                        transactions.append(current_tx)

                    uscita  = _parse_amount(dare_ws[0])  if dare_ws  else None
                    entrata = _parse_amount(avere_ws[0]) if avere_ws else None

                    # Riga senza importo e senza descrizione = riga spuria, scarta
                    if not uscita and not entrata and not desc_inline:
                        current_tx = None
                        continue

                    try:    d_fmt = datetime.strptime(data_val,'%d/%m/%Y').strftime('%Y-%m-%d')
                    except: d_fmt = data_val

                    current_tx = {
                        'data_op'    : d_fmt,
                        'uscita'     : uscita,
                        'entrata'    : entrata,
                        'descrizione': desc_inline,
                        'causale'    : '',
                        'conto_dare' : '',
                        'conto_avere': '',
                        'numero_doc' : '',
                    }
                else:
                    # Riga di continuazione: tutto il testo non-skip va alla descrizione
                    if current_tx:
                        extra_words = [
                            w['text'] for w in sorted(rw, key=lambda x: x['x0'])
                            if w['text'] not in SKIP_KW
                               and not DATE_RE.match(w['text'])   # date già gestite in split_row
                               and not AMOUNT_RE.match(w['text'])
                               and (w['x0'] + w['x1'])/2 >= desc_x_start  # solo zona descrizione
                        ]
                        # Includi anche date nella zona descrizione
                        date_in_desc = [
                            w['text'] for w in sorted(rw, key=lambda x: x['x0'])
                            if DATE_RE.match(w['text']) and w['x0'] > 120
                        ]
                        extra = ' '.join(extra_words + date_in_desc)
                        if extra:
                            current_tx['descrizione'] = (current_tx['descrizione'] + ' ' + extra).strip()

            if current_tx:
                transactions.append(current_tx)

    # Rimuovi righe senza importo (residui spurii)
    transactions = [tx for tx in transactions if tx.get('entrata') or tx.get('uscita')]

    # Pulizia descrizioni (prima della dedup, così usiamo la descrizione completa)
    for tx in transactions:
        tx['descrizione'] = re.sub(r'\s+', ' ', tx['descrizione']).strip()[:255]

    # Deduplicazione: rimuove solo exact duplicates da overlap tra pagine
    # Usa descrizione COMPLETA ([:255]) per non scartare righe diverse come
    # le due RECUP. SPESE COMUNICAZIONI con rapporti diversi (1344320 / 1349014)
    seen = set()
    final = []
    for tx in transactions:
        key = (tx['data_op'], tx['uscita'], tx['entrata'], tx['descrizione'])
        if key not in seen:
            seen.add(key)
            final.append(tx)

    return final, saldo_iniziale, saldo_finale
