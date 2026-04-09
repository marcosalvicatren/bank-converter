"""
Auto-discovery connettori banca.
Ogni connettore nella cartella espone:
  - get_name() -> str
  - get_id()   -> str
  - extract(pdf_file_or_path) -> (transactions, saldo_iniziale, saldo_finale)
"""
import importlib, pkgutil, os, sys

def list_connectors():
    """Ritorna dict {id: modulo} di tutti i connettori disponibili."""
    connectors = {}
    pkg_dir = os.path.dirname(__file__)
    for _, name, _ in pkgutil.iter_modules([pkg_dir]):
        if name.startswith('_'):
            continue
        try:
            mod = importlib.import_module(f'connectors.{name}')
            if hasattr(mod, 'get_id') and hasattr(mod, 'get_name') and hasattr(mod, 'extract'):
                connectors[mod.get_id()] = mod
        except Exception:
            pass
    return connectors

def get_connector_options():
    """Ritorna lista di (label, id) per il menu Streamlit."""
    c = list_connectors()
    return [(mod.get_name(), cid) for cid, mod in c.items()]
