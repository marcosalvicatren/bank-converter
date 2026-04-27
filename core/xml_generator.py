"""
Generatore XML Prima Nota — tracciato SchemaImportazionePrimaNotaV2.xsd
Invariato rispetto allo script originale.
"""
from lxml import etree
import re as _re

def _fmt_importo(val, sep='.'):
    if val == int(val): return str(int(val))
    return f"{val:.2f}".replace('.', sep)

def _sub(p, tag, text):
    el = etree.SubElement(p, tag)
    el.text = str(text) if text else ""
    return el

def _riga(parent, conto, importo, desc, sep='.'):
    det = etree.SubElement(parent, "SezioneContoDettaglioNonIva")
    _sub(det, "Conto",           conto)
    _sub(det, "ImponibileConto", _fmt_importo(importo, sep))
    _sub(det, "Descrizione",     desc[:255])

def generate_xml(transactions, output_path,
                 xsd_filename="SchemaImportazionePrimaNotaV2.xsd",
                 dec_sep='.', doc_prefix="MOV"):
    """
    Genera il file XML a partire dalle transazioni.
    Ritorna lista di avvisi (campi mancanti).
    """
    errori = []
    XSI    = "http://www.w3.org/2001/XMLSchema-instance"
    root   = etree.Element("PrimaNotaXsd", nsmap={"xsi": XSI})
    root.set(f"{{{XSI}}}noNamespaceSchemaLocation", xsd_filename)
    lista  = etree.SubElement(root, "ListaPrimaNota")

    for i, tx in enumerate(transactions, 1):
        dare_az  = tx.get('dare_az')
        avere_az = tx.get('avere_az')
        # Compatibilità con entrambe le strutture dati
        if dare_az is None:  dare_az  = tx.get('entrata')
        if avere_az is None: avere_az = tx.get('uscita')

        conto_d = tx.get('conto_dare',  '').strip()
        conto_a = tx.get('conto_avere', '').strip()
        causale = tx.get('causale',     '').strip()
        desc    = tx.get('descrizione', '')

        if not conto_d:  errori.append(f"Riga {i}: Conto Dare mancante ('{desc[:40]}')")
        if not conto_a:  errori.append(f"Riga {i}: Conto Avere mancante ('{desc[:40]}')")
        if not causale:  errori.append(f"Riga {i}: Causale mancante ('{desc[:40]}')")

        imp = etree.SubElement(lista, "PrimaNotaImportazione")
        ni  = etree.SubElement(imp,   "PrimaNotaNonIva")
        dg  = etree.SubElement(ni,    "PrimaNotaDatiGenerici")

        _sub(dg, "CausaleContabile",  causale)
        ndoc = tx.get('numero_doc', '').strip()
        if not ndoc:
            ndoc = f"{doc_prefix}-{tx['data_op'].replace('-','')}-{i:03d}"
        _sub(dg, "NumeroDocumento",   ndoc)
        _sub(dg, "DataDocumento",     tx['data_op'])
        _sub(dg, "DataRegistrazione", tx.get('data_reg') or tx['data_op'])

        sc = etree.SubElement(ni,  "PrimaNotaSezioneConto")
        ld = etree.SubElement(sc,  "ListaDettaglioSezioneConto")

        importo = dare_az if dare_az else avere_az
        if importo:
            _riga(ld, conto_d,  importo, desc, dec_sep)
            _riga(ld, conto_a, -importo, desc, dec_sep)

    xml_bytes = etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)
    xml_str   = xml_bytes.decode("UTF-8")

    def _swap_attrs(m):
        tag   = m.group(0)
        xmlns = _re.search(r'xmlns:xsi="[^"]*"', tag).group()
        nons  = _re.search(r'xsi:noNamespaceSchemaLocation="[^"]*"', tag).group()
        return f'<PrimaNotaXsd {nons} {xmlns}>'
    xml_str = _re.sub(r'<PrimaNotaXsd[^>]+>', _swap_attrs, xml_str, count=1)

    with open(output_path, "w", encoding="UTF-8") as fh:
        fh.write(xml_str)

    return errori

def generate_xml_bytes(transactions,
                       xsd_filename="SchemaImportazionePrimaNotaV2.xsd",
                       dec_sep='.', doc_prefix="MOV"):
    """
    Come generate_xml ma ritorna (xml_string, errori) senza scrivere su file.
    Usato da Streamlit per il download diretto.
    """
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix='.xml', delete=False) as tmp:
        tmp_path = tmp.name
    errori = generate_xml(transactions, tmp_path, xsd_filename, dec_sep, doc_prefix)
    with open(tmp_path, 'r', encoding='utf-8') as f:
        xml_str = f.read()
    os.unlink(tmp_path)
    return xml_str, errori
