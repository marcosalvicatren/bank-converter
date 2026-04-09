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

    SKIP_KW = [
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
        '#StayLocalBeGlobal','SPORTELLO','UNICO','INTERNAZIONALIZZAZIONE',
        'PRODOTTI','BANCARI','FINANZIARI','FORMAZIONE','EVENTI','SERVIZI',
        'EUROPA','COLLABORAZIONI','SCANSIONA','QR-CODE','INFO',
        'businessclass@popso.it','tel.','0342','528','783',
        'www.popso.it/estero','https://businessschool.popso.it/',
    ]

    saldo_iniziale = saldo_finale = None
    transactions = []

    # Supporto sia path che file-like
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

            # Calibrazione colonne
            dare_x_center = avere_x_center = None
            for w in words:
                if w['text'] == 'Dare'  and w['top'] < 120: dare_x_center  = (w['x0']+w['x1'])/2
                if w['text'] == 'Avere' and w['top'] < 120: avere_x_center = (w['x0']+w['x1'])/2
            if dare_x_center  is None: dare_x_center  = 220
            if avere_x_center is None: avere_x_center = 310
            mid_da       = (dare_x_center + avere_x_center) / 2
            desc_x_start = avere_x_center + 60

            # Raggruppa per riga
            rows_dict = defaultdict(list)
            for w in words:
                rows_dict[round(w['top'] / 4) * 4].append(w)
            sorted_rows = sorted(rows_dict.items())

            def row_text_full(rw):
                return ' '.join(w['text'] for w in sorted(rw, key=lambda x: x['x0']))

            def is_header_or_skip(rw):
                txt = row_text_full(rw)
                return any(k in txt for k in [
                    'Data','Valuta','Movimenti','Dare','Avere','Descrizione operazione',
                    'Saldo iniziale','Saldo finale','Totale movimenti','Giacenza media',
                    'BBAN','IBAN','BIC','Pagina','Situazione al','Conto Corrente',
                    'Filiale di','LIRFO001','POSOIT22','Banca Popolare','BPER',
                    'IMPOSTA DI BOLLO','Si rammenta','BANCA POPOLARE DI SONDRIO',
                    'Fondata nel','Codice Fiscale','Partita IVA',
                    'SPORTELLO','UNICO PER','INTERNAZIONALIZZAZIONE',
                    'Documento numero','messaggio protegge','trasparenza',
                ])

            def split_row(rw):
                sorted_w = sorted(rw, key=lambda x: x['x0'])
                dare_words = avere_words = []
                desc_words = []
                dates_found = []
                for w in sorted_w:
                    cx = (w['x0']+w['x1'])/2
                    t  = w['text']
                    if DATE_RE.match(t):
                        dates_found.append((cx, t))
                    elif AMOUNT_RE.match(t):
                        if cx < mid_da: dare_words  = dare_words  + [t]
                        else:           avere_words = avere_words + [t]
                    elif cx >= desc_x_start:
                        desc_words.append(t)
                dates_found.sort(key=lambda x: x[0])
                data_val = dates_found[0][1] if dates_found else None
                return data_val, dare_words, avere_words, ' '.join(desc_words)

            current_tx = None
            for top, rw in sorted_rows:
                if is_header_or_skip(rw): continue
                txt_full = row_text_full(rw)
                if not txt_full.strip(): continue
                data_val, dare_ws, avere_ws, desc_inline = split_row(rw)

                if data_val:
                    if current_tx: transactions.append(current_tx)
                    uscita  = _parse_amount(dare_ws[0])  if dare_ws  else None
                    entrata = _parse_amount(avere_ws[0]) if avere_ws else None
                    if uscita and not entrata and not desc_inline:
                        current_tx = None; continue
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
                    if current_tx and desc_inline:
                        current_tx['descrizione'] = (current_tx['descrizione']+' '+desc_inline).strip()
                    elif current_tx:
                        extra = ' '.join(
                            w['text'] for w in sorted(rw, key=lambda x: x['x0'])
                            if w['text'] not in SKIP_KW
                               and not DATE_RE.match(w['text'])
                               and not AMOUNT_RE.match(w['text'])
                        )
                        if extra:
                            current_tx['descrizione'] = (current_tx['descrizione']+' '+extra).strip()

            if current_tx:
                transactions.append(current_tx)

    # Pulizia e deduplicazione
    for tx in transactions:
        tx['descrizione'] = re.sub(r'\s+', ' ', tx['descrizione']).strip()[:255]

    seen = set(); unique = []
    for tx in transactions:
        key = (tx['data_op'], tx['uscita'], tx['entrata'], tx['descrizione'][:60])
        if key not in seen:
            seen.add(key); unique.append(tx)

    return unique, saldo_iniziale, saldo_finale
