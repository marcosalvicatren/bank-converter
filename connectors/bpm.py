"""
Connettore Banco BPM – Estratto Conto Unico (formato digitale PDF).
"""
import re
from datetime import datetime
from collections import defaultdict


def get_id():         return "bpm"
def get_name():       return "Banco BPM"
def get_doc_prefix(): return "BPM"


def _parse_amount(s):
    s = str(s).strip().replace('\xa0','').replace(' ','')
    s = re.sub(r'^[+\-−]','',s).strip()
    try:    return float(s.replace('.','').replace(',','.'))
    except: return None

def _parse_date(s):
    for fmt in ('%d/%m/%y','%d/%m/%Y'):
        try: return datetime.strptime(s.strip(),fmt).strftime('%Y-%m-%d')
        except: pass
    return None

DATE_RE   = re.compile(r'^\d{2}/\d{2}/\d{2}(?:\d{2})?$')
AMOUNT_RE = re.compile(r'^\d{1,3}(?:\.\d{3})*,\d{2}$')
FUSED_RE  = re.compile(r'^(\d{1,3}(?:\.\d{3})*,\d{2})(.+)$')

TABLE_END = [re.compile(p, re.IGNORECASE) for p in [
    r'^\*1\s',r'^\*1 DATA',
    r'^RIASSUNTO SCALARE',r"^Questo e' il riassunto",
    r'^INTERESSI MATURATI',r'^COMPETENZE LIQUIDATE',
    r'^DETTAGLIO SALDI',r'^SPESE$',r'^RIEPILOGO',
    r'^SEGNALAZIONI AI FINI',r'^IMPOSTA DI BOLLO',
    r'^Gentile Cliente',r'^La informiamo',
    r'^Le ricordiamo',r'^Al fine di',
]]

SKIP = [re.compile(p, re.IGNORECASE) for p in [
    r'^ATM\b',r'^WEB\b',r'^APP\b',
    r'^DATA\s+CONTABILE',r'^DATA\s+VALUTA',r'^DESCRIZIONE\s+DELLE',
    r'^Pagina \d+',r'^INDEX:',
    r'^ESTRATTO\s+CONTO\s+UNICO',r'^DIVISA\s+EUR',
    r'^AL\s+\d{2}\.\d{2}',r'^INVIO\s+N\.',
    r'^BANCO\s+BPM',r'^PARTNER\s+ISTITUZIONALE',
    r'^Gestisci\s+online',r'^Puoi\s+farlo',r'^scarica\s+You',
    r'^ESTRATTO\s+CONTO$',r'^COORDINATE\s+BANCARIE',
    r'^IT\s+\d{2}\s+[A-Z]',r'^CIN\s+ABI',
    r'^PRESSO$',r'^SWIFT$',r'^BAPPIT',r'^ECITA',
    r'^VIA\s+',r'^\d{5}\s+[A-Z]',r'^Intestato\s+a',
    r'^Data di riferimento',r'^Del conto',
    r'^\d{2}\.\d{2}\.\d{4}$',r'^\d{5}/\d{12}$',
    r'^USCITE\b',r'^ENTRATE\b',
]]

def _is_end(t):
    for p in TABLE_END:
        if p.match(t.strip()): return True
    return False

def _is_skip(t):
    t=t.strip()
    if not t: return True
    for p in SKIP:
        if p.match(t): return True
    return False

def _expand(sorted_w, desc_x):
    out=[]
    for w in sorted_w:
        m=FUSED_RE.match(w['text'])
        if m and w['x0'] < desc_x + 40:
            out.append({'text':m.group(1),'x0':w['x0'],'x1':w['x0']+20,'top':w['top']})
            out.append({'text':m.group(2),'x0':max(desc_x, w['x0']+21),'x1':w['x1'],'top':w['top']})
        else:
            out.append(w)
    return out


def extract(pdf_source):
    import pdfplumber

    saldo_iniziale=saldo_finale=None
    transactions=[]

    with pdfplumber.open(pdf_source) as pdf:
        for page in pdf.pages:
            words=page.extract_words(keep_blank_chars=False, x_tolerance=3, y_tolerance=3)
            if not words: continue

            full_text=page.extract_text() or ''

            # Saldi dal testo
            for line in full_text.split('\n'):
                ls=re.sub(r'(\d{1,3}(?:\.\d{3})*,\d{2})([A-Za-z])',r'\1 \2',line)
                m=re.match(r'\d{2}/\d{2}/\d{2,4}\s+([\d\.]+,\d{2})\s+SALDO INIZIALE',ls,re.I)
                if m and saldo_iniziale is None: saldo_iniziale=_parse_amount(m.group(1))
                m2=re.match(r'\d{2}/\d{2}/\d{2,4}\s+([\d\.]+,\d{2})\s+SALDO FINALE',ls,re.I)
                if m2: saldo_finale=_parse_amount(m2.group(1))

            rows_dict=defaultdict(list)
            for w in words:
                rows_dict[round(w['top']/4)*4].append(w)
            sorted_rows=sorted(rows_dict.items())

            # Cerca header USCITE/ENTRATE
            table_start_top=None
            uscite_x=250; entrate_x=317; desc_x=342

            for top, rw in sorted_rows:
                row_txt=' '.join(w['text'] for w in sorted(rw, key=lambda x: x['x0']))
                # Header può essere su più righe vicine (top 100-160)
                if 'USCITE' in row_txt or 'ENTRATE' in row_txt:
                    if table_start_top is None or top <= table_start_top + 20:
                        if table_start_top is None: table_start_top = top
                        for w in rw:
                            if w['text']=='USCITE':      uscite_x=(w['x0']+w['x1'])/2
                            elif w['text']=='ENTRATE':
                                entrate_x=(w['x0']+w['x1'])/2
                                desc_x = w['x1'] + 15  # desc inizia dopo x1 di ENTRATE
                elif table_start_top is not None:
                    break  # dopo l'header, smetti di cercare

            if table_start_top is None: continue

            # Fine tabella
            table_end_top=None
            for top, rw in sorted_rows:
                if top <= table_start_top+20: continue
                row_txt=' '.join(w['text'] for w in sorted(rw, key=lambda x: x['x0']))
                if _is_end(row_txt):
                    table_end_top=top; break

            table_rows=[(t,rw) for t,rw in sorted_rows
                        if t>table_start_top+20
                        and (table_end_top is None or t<table_end_top)]

            mid_ue=(uscite_x+entrate_x)/2
            current_tx=None

            for top, rw in table_rows:
                sorted_w=sorted(rw, key=lambda x: x['x0'])
                row_txt=' '.join(w['text'] for w in sorted_w)

                if _is_skip(row_txt): continue

                # Saldo inline
                ls_n=re.sub(r'(\d{1,3}(?:\.\d{3})*,\d{2})([A-Za-z])',r'\1 \2',row_txt)
                m_si=re.search(r'([\d\.]+,\d{2})\s+SALDO INIZIALE',ls_n,re.I)
                m_sf=re.search(r'([\d\.]+,\d{2})\s+SALDO FINALE',ls_n,re.I)
                if m_si:
                    if saldo_iniziale is None: saldo_iniziale=_parse_amount(m_si.group(1))
                    if current_tx: transactions.append(current_tx); current_tx=None
                    continue
                if m_sf:
                    saldo_finale=_parse_amount(m_sf.group(1))
                    if current_tx: transactions.append(current_tx); current_tx=None
                    continue

                expanded=_expand(sorted_w, desc_x)

                date_ws=[w for w in expanded if DATE_RE.match(w['text']) and w['x0']<desc_x]
                data_op=_parse_date(date_ws[0]['text']) if date_ws else None

                neg=False; uscita=entrata=None
                for w in expanded:
                    cx=(w['x0']+w['x1'])/2
                    if w['x0']>=desc_x: continue
                    if w['text'] in ('-','−'): neg=True; continue
                    if AMOUNT_RE.match(w['text']) and cx<desc_x:
                        amt=_parse_amount(w['text'])
                        if cx<=mid_ue: uscita=amt
                        else:          entrata=amt
                        neg=False

                desc_parts=[w['text'] for w in expanded
                             if w['x0']>=desc_x and w['text'] not in ('-','−')]
                desc=re.sub(r'\s+',' ',' '.join(desc_parts)).strip()

                if data_op and (uscita is not None or entrata is not None):
                    if current_tx: transactions.append(current_tx)
                    current_tx={
                        'data_op':data_op,'uscita':uscita,'entrata':entrata,
                        'descrizione':desc[:255],'causale':'',
                        'conto_dare':'','conto_avere':'','numero_doc':'',
                    }
                elif not data_op and desc and current_tx:
                    current_tx['descrizione']=(current_tx['descrizione']+' '+desc).strip()[:255]

            if current_tx: transactions.append(current_tx)

    transactions=[tx for tx in transactions
                  if (tx.get('uscita') or tx.get('entrata')) and tx.get('descrizione')]
    for tx in transactions:
        tx['descrizione']=re.sub(r'\s+',' ',tx['descrizione']).strip()[:255]

    seen=set(); final=[]
    for tx in transactions:
        key=(tx['data_op'],tx['uscita'],tx['entrata'],tx['descrizione'])
        if key not in seen:
            seen.add(key); final.append(tx)

    return final, saldo_iniziale, saldo_finale
