# Bank Statement Converter
**Estratto Conto → Prima Nota XML** — Multi-banca, con regole di imputazione automatica

## Funzionalità
- **Percorso 1 (diretto):** PDF → revisione in GUI → XML
- **Percorso 2 (con Excel):** PDF → download Excel → compila → ricarica → XML
- **Regole di imputazione** modificabili dalla GUI senza toccare il codice
- **Multi-banca:** aggiungi un nuovo connettore senza cambiare nient'altro
- **Validazione** prima dell'XML con report anomalie

---

## Prima pubblicazione (tutto da browser, nessun terminale)

### 1. Crea un account GitHub
Vai su [github.com](https://github.com) → **Sign up**.

### 2. Crea un nuovo repository
- Clicca **+** in alto a destra → **New repository**
- Nome: `bank-converter`
- Visibilità: **Private** (consigliato)
- Non spuntare nulla
- Clicca **Create repository**

### 3. Carica i file
- Nel repository appena creato, clicca **uploading an existing file**
- Trascina tutti i file e le cartelle dello zip nella finestra
- Scrivi un messaggio nel campo **Commit changes** (es. "Prima versione")
- Clicca **Commit changes**

> ⚠️ GitHub da browser non carica cartelle in modo diretto su tutti i browser.
> Se hai problemi, carica prima i file della cartella radice, poi entra nella
> cartella `connectors/`, clicca **Add file → Upload files** e carica i file di
> quella cartella. Ripeti per `core/` e `data/`.

### 4. Deploy su Streamlit Cloud
- Vai su [share.streamlit.io](https://share.streamlit.io) → **Sign up with GitHub**
- Clicca **New app**
- Repository: seleziona `bank-converter`
- Branch: `main`
- Main file path: `app.py`
- Clicca **Deploy**

In 2-3 minuti il tool è online all'indirizzo `https://TUO_UTENTE-bank-converter.streamlit.app`.
Basta condividere quel link con i collaboratori — aprono il browser e usano il tool.

---

## Aggiornamenti futuri

### Modificare un file esistente (es. aggiungere una regola via codice)
1. Vai su [github.com](https://github.com) → apri il repository
2. Clicca sul file da modificare (es. `data/regole.json`)
3. Clicca l'icona **matita** ✏️ in alto a destra
4. Fai le modifiche direttamente nel browser
5. Clicca **Commit changes** → **Commit changes**

Streamlit si aggiorna automaticamente entro qualche minuto.

### Aggiungere un file nuovo (es. un nuovo connettore banca)
1. Vai su [github.com](https://github.com) → apri il repository
2. Entra nella cartella dove vuoi aggiungere il file (es. `connectors/`)
3. Clicca **Add file → Create new file**
4. Dai un nome al file (es. `biper_banca.py`) e incolla il contenuto
5. Clicca **Commit changes**

### Sostituire un file intero (es. nuova versione di app.py)
1. Vai su [github.com](https://github.com) → apri il repository
2. Entra nella cartella giusta e clicca sul file
3. Clicca l'icona **matita** ✏️ → seleziona tutto → incolla il nuovo contenuto
4. Clicca **Commit changes**

---

## Uso in locale (opzionale)

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Aggiungere una nuova banca

1. Crea il file `connectors/nuova_banca.py`
2. Implementa le tre funzioni obbligatorie:

```python
def get_id():
    return "nome_univoco"

def get_name():
    return "Nome Banca (visibile nel menu)"

def extract(pdf_source):
    # Logica specifica di estrazione
    # pdf_source può essere path stringa o file-like object
    return transactions, saldo_iniziale, saldo_finale
```

3. Streamlit lo rileva automaticamente al prossimo avvio — zero modifiche al resto del codice.

## Struttura regole (`data/regole.json`)

```json
{
  "id": "R001",
  "nome": "Descrizione leggibile",
  "parole_chiave": ["KEYWORD1", "KEYWORD2"],
  "tipo_movimento": "uscita",   // "entrata", "uscita" o "entrambi"
  "causale": "BAN",
  "conto_dare": "68000",
  "conto_avere": "50000",
  "attiva": true
}
```

La prima regola che matcha (parola chiave trovata nella descrizione + tipo movimento corretto) viene applicata. I campi lasciati vuoti non sovrascrivono quelli già compilati.

## Passaggio BPS → Biper Banca

Quando cambierà il formato:
- Se il formato cambia completamente: crea `connectors/biper_banca.py`
- Se cambia solo qualche dettaglio: aggiorna `connectors/bps.py`
- Il menu si aggiorna automaticamente

## Tracciato XML

`SchemaImportazionePrimaNotaV2.xsd` — invariato rispetto allo script originale.
