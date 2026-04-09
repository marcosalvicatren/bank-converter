"""
Validazione transazioni prima della generazione XML.
"""

REQUIRED_FIELDS = ['causale', 'conto_dare', 'conto_avere']
FIELD_LABELS = {
    'causale':     'Causale',
    'conto_dare':  'Conto Dare',
    'conto_avere': 'Conto Avere',
    'data_op':     'Data Operazione',
}

def validate(transactions):
    """
    Controlla ogni riga e raccoglie gli errori.
    Ritorna (righe_ok, righe_ko, lista_errori).
    
    Ogni errore è un dict: {riga, campo, descrizione, messaggio}
    """
    errors   = []
    rows_ok  = []
    rows_ko  = []

    for i, tx in enumerate(transactions, 1):
        row_errors = []

        for field in REQUIRED_FIELDS:
            val = tx.get(field, '').strip() if tx.get(field) else ''
            if not val:
                row_errors.append({
                    'riga':        i,
                    'campo':       FIELD_LABELS.get(field, field),
                    'descrizione': tx.get('descrizione', '')[:50],
                    'messaggio':   f"Riga {i}: {FIELD_LABELS.get(field, field)} mancante — {tx.get('descrizione','')[:50]}"
                })

        if not tx.get('data_op'):
            row_errors.append({
                'riga':        i,
                'campo':       'Data Operazione',
                'descrizione': tx.get('descrizione', '')[:50],
                'messaggio':   f"Riga {i}: Data Operazione mancante"
            })

        importo = tx.get('dare_az') or tx.get('entrata') or tx.get('avere_az') or tx.get('uscita')
        if not importo:
            row_errors.append({
                'riga':        i,
                'campo':       'Importo',
                'descrizione': tx.get('descrizione', '')[:50],
                'messaggio':   f"Riga {i}: Importo mancante"
            })

        if row_errors:
            errors.extend(row_errors)
            rows_ko.append(tx)
        else:
            rows_ok.append(tx)

    return rows_ok, rows_ko, errors

def validation_report(errors):
    """
    Raggruppa gli errori per campo per mostrare un report leggibile.
    """
    by_field = {}
    for e in errors:
        campo = e['campo']
        by_field.setdefault(campo, []).append(e)
    return by_field
