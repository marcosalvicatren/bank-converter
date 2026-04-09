"""
Motore regole di imputazione automatica.
Le regole vengono caricate da data/regole.json e applicate alle transazioni.
"""
import json, os, uuid
from pathlib import Path

RULES_PATH = Path(__file__).parent.parent / "data" / "regole.json"

def load_rules():
    if not RULES_PATH.exists():
        return []
    with open(RULES_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_rules(rules):
    RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RULES_PATH, 'w', encoding='utf-8') as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)

def apply_rules(transactions, rules=None):
    """
    Applica le regole attive a ogni transazione.
    Restituisce le transazioni con causale/conti pre-compilati dove c'è match.
    """
    if rules is None:
        rules = load_rules()

    active_rules = [r for r in rules if r.get('attiva', True)]

    for tx in transactions:
        desc_upper = tx.get('descrizione', '').upper()
        tipo = 'entrata' if tx.get('entrata') else 'uscita'

        for rule in active_rules:
            # Controlla tipo movimento (se specificato)
            rule_tipo = rule.get('tipo_movimento', '')
            if rule_tipo and rule_tipo != tipo:
                continue

            # Controlla parole chiave (almeno una deve matchare)
            keywords = rule.get('parole_chiave', [])
            if not any(kw.upper() in desc_upper for kw in keywords):
                continue

            # Match trovato: applica solo i campi compilati nella regola
            if rule.get('causale') and not tx.get('causale'):
                tx['causale'] = rule['causale']
            if rule.get('conto_dare') and not tx.get('conto_dare'):
                tx['conto_dare'] = rule['conto_dare']
            if rule.get('conto_avere') and not tx.get('conto_avere'):
                tx['conto_avere'] = rule['conto_avere']
            # Prima regola che matcha vince, poi stop
            break

    return transactions

def new_rule_template():
    return {
        "id": f"R{str(uuid.uuid4())[:6].upper()}",
        "nome": "",
        "parole_chiave": [],
        "tipo_movimento": "entrambi",
        "causale": "",
        "conto_dare": "",
        "conto_avere": "",
        "attiva": True
    }

def match_summary(transactions, rules=None):
    """
    Ritorna statistiche: quante righe hanno tutti i campi obbligatori compilati.
    """
    if rules is None:
        rules = load_rules()
    txs_copy = [dict(tx) for tx in transactions]
    txs_copy = apply_rules(txs_copy, rules)

    total   = len(txs_copy)
    ok      = sum(1 for tx in txs_copy if tx.get('causale') and tx.get('conto_dare') and tx.get('conto_avere'))
    missing = total - ok
    return {'total': total, 'ok': ok, 'missing': missing, 'transactions': txs_copy}
