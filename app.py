"""
Bank Statement Converter — Estratto Conto → Prima Nota XML
Streamlit app multi-banca con regole di imputazione dinamiche.
"""
import streamlit as st
import sys, os, json
from pathlib import Path

# Assicura che i moduli locali siano nel path
sys.path.insert(0, str(Path(__file__).parent))

from connectors import get_connector_options, list_connectors
from core.rules_engine import load_rules, save_rules, apply_rules, new_rule_template
from core.validator import validate, validation_report
from core.xml_generator import generate_xml_bytes
from core.excel_handler import create_xlsx_bytes, read_xlsx_bytes

# ─── Config pagina ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Estratto Conto → Prima Nota",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* Font e colori base */
  html, body, [class*="css"] { font-family: 'Inter', 'Segoe UI', sans-serif; }

  /* Header personalizzato */
  .app-header {
    background: linear-gradient(135deg, #1e3a5f 0%, #2d5a8e 100%);
    color: white;
    padding: 20px 28px 16px 28px;
    border-radius: 10px;
    margin-bottom: 24px;
  }
  .app-header h1 { color: white; font-size: 1.6rem; margin: 0; font-weight: 700; }
  .app-header p  { color: #b8d4f0; font-size: 0.85rem; margin: 4px 0 0 0; }

  /* Step badges */
  .step-badge {
    background: #1e3a5f;
    color: white;
    border-radius: 50%;
    width: 28px; height: 28px;
    display: inline-flex;
    align-items: center; justify-content: center;
    font-weight: 700; font-size: 0.9rem;
    margin-right: 8px;
  }

  /* Card sezione */
  .section-card {
    background: #f8f9fb;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 20px 24px;
    margin-bottom: 16px;
  }

  /* Alert validazione */
  .alert-ok   { background:#e8f5e9; border-left:4px solid #4caf50; padding:12px 16px; border-radius:6px; margin:8px 0; }
  .alert-warn { background:#fff8e1; border-left:4px solid #ff9800; padding:12px 16px; border-radius:6px; margin:8px 0; }
  .alert-err  { background:#fce4ec; border-left:4px solid #e53935; padding:12px 16px; border-radius:6px; margin:8px 0; }

  /* Tabella movimenti */
  .mov-table th { background:#1e3a5f; color:white; font-size:0.8rem; padding:8px; }
  .mov-table td { font-size:0.82rem; padding:6px 8px; border-bottom:1px solid #eee; }
  .mov-entrata  { color: #2e7d32; font-weight: 500; }
  .mov-uscita   { color: #c62828; font-weight: 500; }

  /* Sidebar */
  [data-testid="stSidebar"] { background: #f0f4f8; }

  /* Bottoni primari */
  .stButton > button[kind="primary"] {
    background: #1e3a5f !important;
    color: white !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
  }

  /* Metriche */
  [data-testid="stMetricValue"] { font-size: 1.4rem !important; color: #1e3a5f; }

  /* Tab */
  .stTabs [data-baseweb="tab"] { font-size: 0.9rem; font-weight: 500; }
  .stTabs [aria-selected="true"] { color: #1e3a5f !important; border-bottom-color: #1e3a5f !important; }

  /* Footer */
  .footer { text-align:center; color:#999; font-size:0.75rem; margin-top:40px; padding-top:16px; border-top:1px solid #eee; }
</style>
""", unsafe_allow_html=True)

# ─── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="app-header">
  <h1>🏦 Estratto Conto → Prima Nota XML</h1>
  <p>Converti l'estratto conto bancario in prima nota XML per il gestionale — multi-banca, con regole di imputazione automatica</p>
</div>
""", unsafe_allow_html=True)

# ─── Session state ──────────────────────────────────────────────────────────────
for key, default in [
    ('transactions', None),
    ('saldo_iniziale', None),
    ('saldo_finale', None),
    ('banca_id', None),
    ('banca_nome', ''),
    ('xlsx_bytes', None),
    ('step', 1),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ─── Sidebar: impostazioni globali ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Impostazioni")

    connector_options = get_connector_options()
    if not connector_options:
        st.error("Nessun connettore trovato nella cartella /connectors/")
        st.stop()

    labels  = [o[0] for o in connector_options]
    ids     = [o[1] for o in connector_options]
    sel_idx = st.selectbox("Banca / Formato", range(len(labels)), format_func=lambda i: labels[i])
    st.session_state.banca_id   = ids[sel_idx]
    st.session_state.banca_nome = labels[sel_idx]

    st.divider()
    st.markdown("### 🏦 Conto Banca")
    conto_banca = st.text_input("Conto Banca *", value="", placeholder="es. 50000",
                                help="Usato come contropartita per tutti i movimenti")
    conto_cassa = st.text_input("Conto Cassa", value="", placeholder="es. 57000",
                                help="Usato per VERSAMENTO CONTANTI")
    conto_spese = st.text_input("Conto Spese Bancarie", value="", placeholder="es. 68000",
                                help="Usato per COMMISSIONI, IMPOSTA DI BOLLO, ecc.")
    causale_def = st.text_input("Causale default", value="BAN", placeholder="es. BAN")

    st.divider()
    st.markdown("### 🔧 XML")
    xsd_fname  = st.text_input("Nome file XSD", value="SchemaImportazionePrimaNotaV2.xsd")
    use_comma  = st.checkbox("Usa VIRGOLA come separatore decimale", value=False)
    dec_sep    = ',' if use_comma else '.'

    st.divider()
    st.markdown(f"**Step corrente:** {st.session_state.step} / 3")
    if st.button("🔄 Ricomincia da capo", use_container_width=True):
        for k in ['transactions','saldo_iniziale','saldo_finale','xlsx_bytes']:
            st.session_state[k] = None
        st.session_state.step = 1
        st.rerun()

# ─── TAB principali ────────────────────────────────────────────────────────────
tab_pdf, tab_revisione, tab_xml, tab_regole = st.tabs([
    "  📄 PASSO 1 · PDF → Dati  ",
    "  📊 PASSO 2 · Revisione  ",
    "  ⚡ PASSO 3 · Genera XML  ",
    "  ⚙️ Gestione Regole  ",
])

# ══════════════════════════════════════════════════════════════════════════════
# PASSO 1 — PDF → Dati
# ══════════════════════════════════════════════════════════════════════════════
with tab_pdf:
    st.markdown("### <span class='step-badge'>1</span> Carica il PDF dell'estratto conto", unsafe_allow_html=True)

    uploaded_pdf = st.file_uploader(
        "Seleziona il PDF dell'estratto conto",
        type=["pdf"],
        help=f"Formato atteso: {st.session_state.banca_nome}"
    )

    if uploaded_pdf:
        col1, col2 = st.columns([3, 1])
        with col2:
            converti = st.button("▶ Estrai movimenti", type="primary", use_container_width=True)

        if converti:
            connectors = list_connectors()
            connector  = connectors.get(st.session_state.banca_id)
            if not connector:
                st.error("Connettore non trovato.")
            else:
                with st.spinner("Estrazione in corso..."):
                    try:
                        txs, si, sf = connector.extract(uploaded_pdf)

                        # Applica regole automatiche con i conti della sidebar
                        rules = load_rules()
                        # Aggiorna i conti nelle regole "generiche" con quelli della sidebar
                        for rule in rules:
                            if not rule.get('conto_dare') and conto_spese and rule['id'] in ('R002','R003','R004'):
                                rule['conto_dare']  = conto_spese
                                rule['conto_avere'] = conto_banca
                            if not rule.get('causale') and causale_def:
                                rule['causale'] = causale_def
                            if rule['id'] == 'R001':  # versamento contanti
                                if conto_banca: rule['conto_dare']  = conto_banca
                                if conto_cassa: rule['conto_avere'] = conto_cassa

                        txs = apply_rules(txs, rules)

                        # Per entrate/uscite generiche con solo conto banca
                        for tx in txs:
                            if not tx.get('causale') and causale_def:
                                tx['causale'] = causale_def
                            if tx.get('entrata') and conto_banca and not tx.get('conto_dare'):
                                tx['conto_dare'] = conto_banca
                            if tx.get('uscita') and conto_banca and not tx.get('conto_avere'):
                                tx['conto_avere'] = conto_banca

                        st.session_state.transactions  = txs
                        st.session_state.saldo_iniziale = si
                        st.session_state.saldo_finale   = sf
                        st.session_state.step = 2

                    except Exception as e:
                        import traceback
                        st.error(f"Errore durante l'estrazione:\n\n{e}")
                        with st.expander("Dettagli tecnici"):
                            st.code(traceback.format_exc())

    # Mostra riepilogo se già estratto
    if st.session_state.transactions:
        txs = st.session_state.transactions
        si  = st.session_state.saldo_iniziale
        sf  = st.session_state.saldo_finale

        te = sum(tx.get('entrata') or 0 for tx in txs)
        tu = sum(tx.get('uscita')  or 0 for tx in txs)

        st.markdown("---")
        st.success(f"✅ {len(txs)} movimenti estratti da **{st.session_state.banca_nome}**")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Movimenti", len(txs))
        c2.metric("Entrate", f"€ {te:,.2f}")
        c3.metric("Uscite",  f"€ {tu:,.2f}")
        if si is not None:
            c4.metric("Saldo iniziale", f"€ {si:,.2f}")

        # Anteprima tabella
        with st.expander("📋 Anteprima movimenti estratti", expanded=True):
            _rows = []
            for tx in txs[:50]:
                _rows.append({
                    "Data": tx['data_op'],
                    "Entrata €": f"{tx['entrata']:,.2f}" if tx.get('entrata') else "",
                    "Uscita €":  f"{tx['uscita']:,.2f}"  if tx.get('uscita')  else "",
                    "Descrizione": tx['descrizione'][:80],
                    "Causale": tx.get('causale',''),
                    "C/Dare":  tx.get('conto_dare',''),
                    "C/Avere": tx.get('conto_avere',''),
                })
            import pandas as pd
            df = pd.DataFrame(_rows)
            st.dataframe(df, use_container_width=True, height=400)
            if len(txs) > 50:
                st.caption(f"... e altri {len(txs)-50} movimenti")

        # Download Excel
        st.markdown("---")
        st.markdown("#### 📥 Scarica Excel (opzionale — Percorso 2)")
        st.caption("Scarica, compila o correggi in Excel, poi ricarica nel Passo 2.")

        xlsx = create_xlsx_bytes(txs, si, banca_nome=st.session_state.banca_nome)
        st.download_button(
            label="⬇️ Scarica Excel movimenti",
            data=xlsx,
            file_name="movimenti_estratto_conto.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

        st.markdown("""
        <div class="alert-ok">
        ✅ <strong>Percorso 1 (diretto):</strong> vai al <strong>Passo 2</strong> per revisionare nella tabella, poi al <strong>Passo 3</strong> per generare l'XML.<br>
        📋 <strong>Percorso 2 (Excel):</strong> scarica il file sopra → compilalo → ricaricalo nel <strong>Passo 2</strong>.
        </div>
        """, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# PASSO 2 — Revisione
# ══════════════════════════════════════════════════════════════════════════════
with tab_revisione:
    st.markdown("### <span class='step-badge'>2</span> Revisione movimenti", unsafe_allow_html=True)

    # Opzione ricarica Excel
    with st.expander("📂 Ricarica da Excel (Percorso 2)", expanded=False):
        st.caption("Se hai scaricato e compilato il file Excel, caricalo qui.")
        uploaded_xlsx = st.file_uploader("Carica Excel compilato", type=["xlsx"], key="xlsx_upload")
        if uploaded_xlsx:
            if st.button("📥 Carica movimenti dall'Excel", type="primary"):
                try:
                    txs = read_xlsx_bytes(uploaded_xlsx.read())
                    st.session_state.transactions = txs
                    st.session_state.step = 2
                    st.success(f"✅ {len(txs)} movimenti caricati dall'Excel.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Errore nella lettura dell'Excel: {e}")

    if not st.session_state.transactions:
        st.info("ℹ️ Nessun dato presente. Completa prima il **Passo 1**.")
    else:
        txs = st.session_state.transactions

        # Validazione live
        rows_ok, rows_ko, errors = validate(txs)
        n_total   = len(txs)
        n_ok      = len(rows_ok)
        n_missing = len(rows_ko)

        col1, col2, col3 = st.columns(3)
        col1.metric("Totale movimenti", n_total)
        col2.metric("✅ Righe complete", n_ok)
        col3.metric("⚠️ Righe incomplete", n_missing, delta=f"-{n_missing}" if n_missing else "0", delta_color="inverse")

        if n_missing > 0:
            report = validation_report(errors)
            with st.expander(f"⚠️ {n_missing} righe con dati mancanti — clicca per dettagli", expanded=True):
                for campo, errs in report.items():
                    st.markdown(f"**{campo}** — {len(errs)} righe:")
                    for e in errs[:10]:
                        st.markdown(f"  - Riga {e['riga']}: *{e['descrizione']}*")
                    if len(errs) > 10:
                        st.caption(f"  ... e altre {len(errs)-10}")
        else:
            st.success("✅ Tutti i campi obbligatori sono compilati. Puoi procedere al Passo 3.")

        # Tabella movimenti
        import pandas as pd
        _rows = []
        for i, tx in enumerate(txs, 1):
            ok = bool(tx.get('causale') and tx.get('conto_dare') and tx.get('conto_avere'))
            _rows.append({
                "#": i,
                "Data":       tx['data_op'],
                "Entrata €":  f"{tx.get('entrata') or tx.get('dare_az',''):,.2f}" if (tx.get('entrata') or tx.get('dare_az')) else "",
                "Uscita €":   f"{tx.get('uscita') or tx.get('avere_az',''):,.2f}"  if (tx.get('uscita') or tx.get('avere_az'))  else "",
                "Descrizione": tx['descrizione'][:80],
                "Causale":    tx.get('causale',''),
                "C/Dare":     tx.get('conto_dare',''),
                "C/Avere":    tx.get('conto_avere',''),
                "✓":          "✅" if ok else "⚠️",
            })
        df = pd.DataFrame(_rows)
        st.dataframe(df, use_container_width=True, height=450,
                     column_config={"✓": st.column_config.TextColumn(width="small")})

        st.caption(f"Totale: {n_total} movimenti  |  ✅ {n_ok} completi  |  ⚠️ {n_missing} incompleti")

# ══════════════════════════════════════════════════════════════════════════════
# PASSO 3 — Genera XML
# ══════════════════════════════════════════════════════════════════════════════
with tab_xml:
    st.markdown("### <span class='step-badge'>3</span> Genera XML Prima Nota", unsafe_allow_html=True)

    if not st.session_state.transactions:
        st.info("ℹ️ Nessun dato presente. Completa prima il **Passo 1**.")
    else:
        txs = st.session_state.transactions
        rows_ok, rows_ko, errors = validate(txs)
        n_ok      = len(rows_ok)
        n_missing = len(rows_ko)

        # Report anomalie
        if n_missing > 0:
            st.markdown(f"""
            <div class="alert-warn">
            ⚠️ <strong>{n_missing} righe incomplete</strong> non verranno incluse nell'XML.<br>
            {n_ok} righe complete saranno esportate.
            </div>
            """, unsafe_allow_html=True)

            with st.expander("📋 Dettaglio righe escluse"):
                for e in errors[:20]:
                    st.markdown(f"- **Riga {e['riga']}** — *{e['campo']}* mancante: _{e['descrizione']}_")
                if len(errors) > 20:
                    st.caption(f"... e altri {len(errors)-20} avvisi")
        else:
            st.markdown("""
            <div class="alert-ok">
            ✅ <strong>Tutti i movimenti sono completi.</strong> L'XML includerà tutte le righe.
            </div>
            """, unsafe_allow_html=True)

        st.markdown("---")

        col1, col2 = st.columns(2)
        with col1:
            genera_completo = st.button(
                f"⚡ Genera XML ({n_ok} movimenti completi)",
                type="primary", use_container_width=True,
                disabled=(n_ok == 0)
            )
        with col2:
            if n_missing > 0:
                genera_tutto = st.button(
                    f"⚡ Genera XML (tutti — {len(txs)} mov., con righe vuote)",
                    use_container_width=True
                )
            else:
                genera_tutto = False

        genera = None
        righe_da_usare = None
        if genera_completo:
            genera = True
            righe_da_usare = rows_ok
        elif genera_tutto:
            genera = True
            righe_da_usare = txs

        if genera and righe_da_usare is not None:
            with st.spinner("Generazione XML in corso..."):
                try:
                    # Normalizza struttura per xml_generator
                    txs_norm = []
                    for tx in righe_da_usare:
                        t = dict(tx)
                        if 'dare_az' not in t:  t['dare_az']  = t.get('entrata')
                        if 'avere_az' not in t: t['avere_az'] = t.get('uscita')
                        txs_norm.append(t)

                    xml_str, avvisi = generate_xml_bytes(txs_norm, xsd_fname, dec_sep)

                    st.success(f"✅ XML generato con {len(righe_da_usare)} movimenti.")

                    st.download_button(
                        label="⬇️ Scarica XML Prima Nota",
                        data=xml_str.encode('utf-8'),
                        file_name="prima_nota.xml",
                        mime="application/xml",
                        use_container_width=True,
                    )

                    if avvisi:
                        with st.expander(f"⚠️ {len(avvisi)} avvisi nella generazione"):
                            for a in avvisi[:20]:
                                st.markdown(f"- {a}")

                    with st.expander("🔍 Anteprima XML (prime 60 righe)"):
                        preview = '\n'.join(xml_str.split('\n')[:60])
                        st.code(preview, language='xml')

                except Exception as e:
                    import traceback
                    st.error(f"Errore nella generazione XML: {e}")
                    with st.expander("Dettagli tecnici"):
                        st.code(traceback.format_exc())

# ══════════════════════════════════════════════════════════════════════════════
# GESTIONE REGOLE
# ══════════════════════════════════════════════════════════════════════════════
with tab_regole:
    st.markdown("### ⚙️ Gestione Regole di Imputazione")
    st.caption("Le regole vengono applicate automaticamente durante l'estrazione PDF. La prima regola che matcha la descrizione viene usata.")

    rules = load_rules()

    # ── Regole esistenti ──────────────────────────────────────────────────────
    st.markdown("#### Regole attive")

    rules_changed = False
    rules_to_delete = []

    for idx, rule in enumerate(rules):
        col_active, col_nome, col_kw, col_tipo, col_caus, col_cd, col_ca, col_del = st.columns(
            [0.5, 2, 3, 1.5, 1.5, 1.5, 1.5, 0.5]
        )
        with col_active:
            new_active = st.checkbox("", value=rule.get('attiva', True), key=f"act_{idx}",
                                     label_visibility="collapsed")
            if new_active != rule.get('attiva', True):
                rule['attiva'] = new_active; rules_changed = True

        with col_nome:
            new_nome = st.text_input("Nome", value=rule.get('nome',''), key=f"nome_{idx}",
                                     label_visibility="collapsed", placeholder="Nome regola")
            if new_nome != rule.get('nome',''):
                rule['nome'] = new_nome; rules_changed = True

        with col_kw:
            kw_str = ', '.join(rule.get('parole_chiave', []))
            new_kw = st.text_input("Parole chiave", value=kw_str, key=f"kw_{idx}",
                                   label_visibility="collapsed", placeholder="keyword1, keyword2")
            new_kw_list = [k.strip() for k in new_kw.split(',') if k.strip()]
            if new_kw_list != rule.get('parole_chiave', []):
                rule['parole_chiave'] = new_kw_list; rules_changed = True

        with col_tipo:
            tipo_opts = ['entrata', 'uscita', 'entrambi']
            tipo_idx  = tipo_opts.index(rule.get('tipo_movimento', 'entrambi')) if rule.get('tipo_movimento','entrambi') in tipo_opts else 2
            new_tipo  = st.selectbox("Tipo", tipo_opts, index=tipo_idx, key=f"tipo_{idx}",
                                     label_visibility="collapsed")
            if new_tipo != rule.get('tipo_movimento'):
                rule['tipo_movimento'] = new_tipo; rules_changed = True

        with col_caus:
            new_caus = st.text_input("Causale", value=rule.get('causale',''), key=f"caus_{idx}",
                                     label_visibility="collapsed", placeholder="es. BAN")
            if new_caus != rule.get('causale',''):
                rule['causale'] = new_caus; rules_changed = True

        with col_cd:
            new_cd = st.text_input("C/Dare", value=rule.get('conto_dare',''), key=f"cd_{idx}",
                                   label_visibility="collapsed", placeholder="es. 50000")
            if new_cd != rule.get('conto_dare',''):
                rule['conto_dare'] = new_cd; rules_changed = True

        with col_ca:
            new_ca = st.text_input("C/Avere", value=rule.get('conto_avere',''), key=f"ca_{idx}",
                                   label_visibility="collapsed", placeholder="es. 68000")
            if new_ca != rule.get('conto_avere',''):
                rule['conto_avere'] = new_ca; rules_changed = True

        with col_del:
            if st.button("🗑", key=f"del_{idx}", help="Elimina regola"):
                rules_to_delete.append(idx)

    # Elimina regole marcate
    if rules_to_delete:
        rules = [r for i, r in enumerate(rules) if i not in rules_to_delete]
        rules_changed = True

    st.divider()

    # Legenda colonne
    col1, col2, col3, col4, col5, col6, col7, col8 = st.columns([0.5, 2, 3, 1.5, 1.5, 1.5, 1.5, 0.5])
    col1.caption("Att.")
    col2.caption("Nome regola")
    col3.caption("Parole chiave (separate da virgola)")
    col4.caption("Tipo mov.")
    col5.caption("Causale")
    col6.caption("Conto Dare")
    col7.caption("Conto Avere")
    col8.caption("Del.")

    st.divider()

    # ── Aggiungi nuova regola ─────────────────────────────────────────────────
    with st.expander("➕ Aggiungi nuova regola", expanded=False):
        c1, c2, c3, c4, c5, c6 = st.columns([2, 3, 1.5, 1.5, 1.5, 1.5])
        with c1: new_nome_r  = st.text_input("Nome regola", placeholder="es. Pagamento stipendi")
        with c2: new_kw_r    = st.text_input("Parole chiave", placeholder="es. STIPENDIO, EMOLUMENTI")
        with c3: new_tipo_r  = st.selectbox("Tipo", ['uscita','entrata','entrambi'])
        with c4: new_caus_r  = st.text_input("Causale", placeholder="es. BAN")
        with c5: new_cd_r    = st.text_input("Conto Dare", placeholder="es. 70000")
        with c6: new_ca_r    = st.text_input("Conto Avere", placeholder="es. 50000")

        if st.button("➕ Aggiungi regola", type="primary"):
            if not new_nome_r or not new_kw_r:
                st.error("Nome e parole chiave sono obbligatori.")
            else:
                new_rule = new_rule_template()
                new_rule['nome']            = new_nome_r
                new_rule['parole_chiave']   = [k.strip() for k in new_kw_r.split(',') if k.strip()]
                new_rule['tipo_movimento']  = new_tipo_r
                new_rule['causale']         = new_caus_r
                new_rule['conto_dare']      = new_cd_r
                new_rule['conto_avere']     = new_ca_r
                rules.append(new_rule)
                save_rules(rules)
                st.success(f"✅ Regola '{new_nome_r}' aggiunta.")
                st.rerun()

    # ── Salva modifiche ───────────────────────────────────────────────────────
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("💾 Salva tutte le modifiche", type="primary", use_container_width=True):
            save_rules(rules)
            st.success("✅ Regole salvate.")
            st.rerun()

    if rules_changed:
        st.warning("⚠️ Hai modifiche non salvate. Clicca **Salva** per confermare.")

    # ── Testa le regole ───────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### 🧪 Testa le regole su una descrizione")
    test_desc = st.text_input("Inserisci una descrizione di test", placeholder="es. PAGAMENTO RATA FINANZIAMENTO MUTUO CHIROGRAFARIO")
    test_tipo = st.radio("Tipo movimento", ['entrata', 'uscita'], horizontal=True)
    if test_desc:
        test_tx = [{'descrizione': test_desc,
                    'entrata': 100 if test_tipo == 'entrata' else None,
                    'uscita':  100 if test_tipo == 'uscita' else None,
                    'causale': '', 'conto_dare': '', 'conto_avere': ''}]
        result = apply_rules(test_tx, rules)[0]
        if result.get('causale') or result.get('conto_dare') or result.get('conto_avere'):
            st.markdown(f"""
            <div class="alert-ok">
            ✅ <strong>Regola trovata!</strong><br>
            Causale: <code>{result.get('causale','—')}</code> &nbsp;|&nbsp;
            Conto Dare: <code>{result.get('conto_dare','—')}</code> &nbsp;|&nbsp;
            Conto Avere: <code>{result.get('conto_avere','—')}</code>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="alert-warn">
            ⚠️ <strong>Nessuna regola corrisponde</strong> a questa descrizione. Il movimento rimarrà da compilare manualmente.
            </div>
            """, unsafe_allow_html=True)

# ─── Footer ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="footer">
  Bank Statement Converter · Multi-banca · Streamlit Cloud
</div>
""", unsafe_allow_html=True)
