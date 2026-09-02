"""
Calendario eventi multi-settore: ClinicalTrials.gov, SEC EDGAR, SAM.gov,
NHTSA, FDA, USPTO PTAB. Ogni evento ha link ufficiale verificabile.
Filtrabile per settore e ticker dello screening.
"""
import datetime
import streamlit as st
import pandas as pd

st.set_page_config(page_title="Calendario", page_icon="📅", layout="wide",
                   initial_sidebar_state="collapsed")

from ui.theme import inject_css, COLORS
from ui.nav import render_navbar, sidebar_nav
from core import event_calendar as EC
from core.data_engine import build_universe

if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = True

inject_css(dark=st.session_state.dark_mode)
render_navbar(title="Calendario")
sidebar_nav()

col = COLORS["dark"] if st.session_state.dark_mode else COLORS["light"]

st.markdown("## Calendario Eventi Multi-Settore")
st.caption(
    "Eventi price-sensitive da fonti regolatorie ufficiali. "
    "Ogni evento ha link diretto verificabile alla fonte primaria. "
    "Alcune date (es. completamento trial) sono stime dello sponsor e possono slittare — "
    "controlla sempre il campo 'Stato data'. Lettura, mai ordine."
)

# ── Carica eventi salvati ──────────────────────────────────
events = EC.load_events()

# ── Pannello controllo ─────────────────────────────────────
with st.expander("📥 Aggiorna eventi dalle fonti"):
    st.markdown(
        "**Fonti con API pubblica gratuita (funzionano subito):**\n"
        "- ClinicalTrials.gov — farmaceutico/biotech, nessuna chiave\n"
        "- SEC EDGAR — 8-K deposit, nessuna chiave\n"
        "- USPTO PTAB — controversie brevetti, nessuna chiave\n\n"
        "**Fonti che richiedono API key gratuita:**\n"
        "- **SAM.gov** (contratti federali aerospaziali):\n"
        "  1. Vai su https://sam.gov → clicca \"Sign In\" → crea account\n"
        "  2. Vai su Account → APIs → richiedi chiave per \"Opportunities (opps) API\"\n"
        "  3. Inserisci la chiave sotto oppure impostala come variabile d'ambiente `SAM_API_KEY`\n"
        "- **FDA** (eventi regolatori farmaceutici):\n"
        "  1. Vai su https://open.fda.gov → clicca \"Get an API Key\"\n"
        "  2. Ricevi la chiave via email (gratuita, no account)\n"
        "  3. Inserisci la chiave sotto oppure impostala come `FDA_API_KEY`\n\n"
        "**Automotive/EV (richiami NHTSA)**: fonte disattivata — l'API NHTSA "
        "non offre un endpoint per \"tutti i richiami di un produttore\", "
        "solo per modello+anno specifici.\n\n"
        "**Tecnologia/Semiconduttori**: nessuna fonte regolatoria strutturata disponibile.\n\n"
        "*Senza API key queste due fonti vengono saltate, le altre funzionano ugualmente.*"
    )

    col_key1, col_key2 = st.columns(2)
    sam_default = st.secrets.get("SAM_API_KEY", "")
    fda_default = st.secrets.get("FDA_API_KEY", "")
    sam_key = col_key1.text_input("SAM.gov API key (opzionale)", value=sam_default,
                                   type="password", key="sam_key_input",
                                   help="Incolla la chiave oppure imposta SAM_API_KEY")
    fda_key = col_key2.text_input("FDA API key (opzionale)", value=fda_default,
                                   type="password", key="fda_key_input",
                                   help="Incolla la chiave oppure imposta FDA_API_KEY")

    if st.button("🔄 Scarica da tutte le fonti", type="primary"):
        with st.spinner("Fetch in corso…"):
            new_events = EC.fetch_all_events(
                sam_key=sam_key or st.secrets.get("SAM_API_KEY"),
                fda_key=fda_key or st.secrets.get("FDA_API_KEY"),
            )
            diag = EC.get_last_diagnostics()
            if new_events:
                EC.save_events(new_events)
                st.success(f"✅ Salvati {len(new_events)} eventi.")
            else:
                st.warning("Nessun evento recuperato. Vedi diagnostica sotto.")
            with st.expander("🔍 Diagnostica fonti (ultimo tentativo)", expanded=not new_events):
                for d in diag:
                    icon = "✅" if d["status"] == "OK" else "⏭️" if d["status"] == "SALTATA" else "❌"
                    st.write(f"{icon} **{d['fonte']}** — {d['status']}"
                             + (f" ({d['count']} risultati)" if d["status"] == "OK" else "")
                             + (f" — {d['dettaglio']}" if d.get("dettaglio") else ""))
            # Diag salvata in session_state: senza questo, lo st.rerun() qui
            # sotto (necessario per aggiornare subito la tabella con i nuovi
            # eventi) ricarica la pagina da zero e cancella l'expander appena
            # disegnato — la diagnostica di fatto non era mai leggibile
            # quando almeno una fonte aveva successo.
            st.session_state["_last_ct_diag"] = diag
            if new_events:
                st.rerun()

    if st.session_state.get("_last_ct_diag"):
        with st.expander("🔍 Diagnostica fonti (ultimo tentativo)"):
            for d in st.session_state["_last_ct_diag"]:
                icon = "✅" if d["status"] == "OK" else "⏭️" if d["status"] == "SALTATA" else "❌"
                st.write(f"{icon} **{d['fonte']}** — {d['status']}"
                         + (f" ({d['count']} risultati)" if d["status"] == "OK" else "")
                         + (f" — {d['dettaglio']}" if d.get("dettaglio") else ""))

    if events:
        st.caption(f"Ultimo aggiornamento: {events[0].get('ultimo_controllo', '—')[:10]}")
        if st.button("🗑 Cancella eventi salvati e riparti"):
            EC.save_events([])
            st.rerun()

if not events:
    st.info(
        "Nessun evento in archivio. Usa 📥 Aggiorna eventi per scaricare "
        "dalle fonti regolatorie."
    )
    st.stop()

# ── Filtri ─────────────────────────────────────────────────
today = datetime.date.today()
universe = build_universe()

settori_disponibili = list(EC.SETTORI)
settore_sel = st.selectbox("Filtra per settore", ["Tutti"] + settori_disponibili)

# ticker presenti nello screening
df_events = pd.DataFrame(events)
tickers_screening = [t for t in universe if t in df_events["ticker"].values]

c1, c2 = st.columns(2)
mostra_solo_screening = c1.checkbox("Solo ticker presenti nello screening", value=True)
solo_recenti_futuri = c2.checkbox(
    "Solo eventi recenti/futuri (da inizio mese)", value=True,
    help="Mostra solo eventi con data dal primo giorno del mese corrente in poi. "
         "A differenza del vecchio filtro 'solo futuri', questo si basa sulla data "
         "reale dell'evento, non sulla fonte: una segnalazione FAERS di questo mese "
         "passerebbe, una di 12 anni fa no."
)

# ── Filtraggio ────────────────────────────────────────────
inizio_mese_corrente = today.replace(day=1)

filtered = []
for e in events:
    if settore_sel != "Tutti" and e.get("settore") != settore_sel:
        continue
    if mostra_solo_screening and e.get("ticker") not in tickers_screening:
        continue
    try:
        d = datetime.date.fromisoformat(e["data_attesa"])
    except Exception:
        continue
    if solo_recenti_futuri and d < inizio_mese_corrente:
        continue
    filtered.append(e)

filtered.sort(key=lambda e: e.get("data_attesa", "9999-99-99"))
total = len(filtered)

# ── Statistiche ────────────────────────────────────────────
stats_by_settore = {}
for e in filtered:
    s = e.get("settore", "Altro")
    stats_by_settore[s] = stats_by_settore.get(s, 0) + 1

stat_cols = st.columns(max(1, len(stats_by_settore)))
for i, (s, cnt) in enumerate(sorted(stats_by_settore.items())):
    stat_cols[i].metric(s, cnt)

st.caption(f"**{total}** eventi filtrati · "
           f"orizzonte: {'da ' + inizio_mese_corrente.isoformat() if solo_recenti_futuri else 'tutti'}")

# ── Vista eventi (tabella + dettaglio) ─────────────────────
SCORE_COLORS = {"Farmaceutico/Biotech": col["accent"],
                "Estrattivo (Mining, Oil&Gas)": col["warning"],
                "Aerospaziale/Difesa": col["positive"],
                "Automotive/EV": col["negative"]}

rows = []
for e in filtered:
    rows.append({
        "Data": e["data_attesa"],
        "Ticker": e.get("ticker") or "—",
        "Nome": e["nome"],
        "Settore": e["settore"],
        "Tipo": e["tipo"],
        "Descrizione": e["descrizione"][:80],
        "Fonte": e["fonte"],
        "Stato data": e.get("stato_data", "—"),
        "Orientamento": "🔮 futuro" if e.get("orientamento", "futuro") == "futuro" else "🕓 passato",
        "Link": e["link_ufficiale"],
        "Verificato": "✅" if e.get("verified") else "❌",
    })

if rows:
    df_view = pd.DataFrame(rows).sort_values("Data").reset_index(drop=True)

    df_view["Link"] = df_view["Link"].apply(
        lambda x: f"[🔗 Apri]({x})" if x.startswith("http") else x)

    column_config = {
        "Link": st.column_config.LinkColumn(
            "Link", help="Apri fonte ufficiale", display_text="🔗",
            width="small",
        ),
    }

    st.dataframe(
        df_view, use_container_width=True, hide_index=True,
        column_config=column_config,
        on_select="rerun", selection_mode="single-row",
        key="tbl_eventi",
    )
else:
    st.info("Nessun evento corrisponde ai filtri selezionati.")

# ── Dettaglio evento selezionato ───────────────
rows_sel = list(
    st.session_state.get("tbl_eventi", {}).get("selection", {}).get("rows", [])
)
if rows_sel and rows_sel[0] < len(filtered):
    ev = filtered[rows_sel[0]]
    st.markdown("---")
    st.markdown(f"### {ev.get('tipo', '—')} — {ev.get('nome', '—')}")
    if ev.get("ticker"):
        st.caption(f"Ticker: `{ev['ticker']}`")
    m1, m2, m3 = st.columns(3)
    m1.metric("Data attesa", ev.get("data_attesa", "—"))
    m2.metric("Settore", ev.get("settore", "—"))
    m3.metric("Fonte", ev.get("fonte", "—"))
    st.markdown(f"**Descrizione**: {ev.get('descrizione', '—')}")
    st.markdown(f"**Link ufficiale**: [{ev.get('link_ufficiale', '—')}]({ev.get('link_ufficiale', '#')})")
    st.markdown(f"**Ultimo controllo**: {ev.get('ultimo_controllo', '—')}")
    st.caption(f"Stato data: {ev.get('stato_data', '—')} · "
               f"Verificato: {'✅' if ev.get('verified') else '❌'}")

    # Wyckoff score se disponibile
    ticker_ev = ev.get("ticker")
    if ticker_ev and ticker_ev != "—":
        try:
            from core.reversal import analyze_ticker
            a = analyze_ticker(ticker_ev)
            if a and a.get("wyckoff", {}).get("n_events", 0) >= 2:
                wyk = a["wyckoff"]
                st.metric("Wyckoff score", f"{wyk['score_10']}/10",
                          help=f"Confidenza: {wyk['confidence']} "
                               f"· Eventi: {'+'.join(wyk['events'])}")
        except Exception:
            pass

# ── Log controlli ──────────────────────────────────────────
with st.expander("📋 Log controlli"):
    try:
        import json
        from pathlib import Path
        log_path = EC.LAST_CHECK_PATH
        if log_path.exists():
            logs = json.loads(log_path.read_text(encoding="utf-8"))
            for l in reversed(logs):
                st.caption(f"{l.get('ts', l.get('time', '—'))[:19]} — {l.get('event', '—')}")
        else:
            st.caption("Nessun log disponibile.")
    except Exception:
        st.caption("Errore lettura log.")
