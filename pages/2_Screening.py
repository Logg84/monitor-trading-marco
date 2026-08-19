"""
Screening: titoli in sconto + alert POC/VWAP + grafico di decelerazione.
Usa volume profile reale. Log di avanzamento per le operazioni lunghe.
"""
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

st.set_page_config(page_title="Screening", page_icon="🎛️", layout="wide",
                   initial_sidebar_state="collapsed")

from ui.theme import inject_css, COLORS, style_fig
from ui.nav import render_navbar, sidebar_nav
from core.data_engine import (
    INDICES_DIR, load_index_constituents, screening,
    get_prices, vwap_anchored, poc_zone_from_profile, bottom_score,
)
from core.watchlist_io import add_entry, load_watchlist

if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = True

inject_css(dark=st.session_state.dark_mode)
render_navbar(title="Screening")
sidebar_nav()

st.markdown("## Screening")
st.caption("Lettura, mai ordine — non è consulenza.")

# Lista indici disponibili: solo i CSV presenti in data/indices.
available = []
if INDICES_DIR.exists():
    available = sorted(p.stem for p in INDICES_DIR.glob("*.csv"))

ALL_INDICES = "📊 VISUALIZZA TUTTI INSIEME"
options = [ALL_INDICES] + available

c1, c2 = st.columns([3, 1])
index_name = c1.selectbox("Indice", options)
run = c2.button("🚀 Avvia screening", type="primary")

if run:
    if not available:
        st.error("Nessun file indice in data/indices. Genera i CSV con scripts/download_indices.py --force e fai commit.")
        st.stop()

    if index_name == ALL_INDICES:
        per_index = {}
        raw_tickers = []
        for n in available:
            tks = load_index_constituents(n)
            per_index[n] = len(tks)
            raw_tickers.extend(tks)
        gross = len(raw_tickers)
        tickers = sorted(set(raw_tickers))
        st.session_state["screening_per_index"] = per_index
        st.session_state["screening_gross"] = gross
    else:
        tickers = load_index_constituents(index_name)
        st.session_state["screening_per_index"] = {index_name: len(tickers)}
        st.session_state["screening_gross"] = len(tickers)

    if not tickers:
        st.error(
            f"Nessun ticker disponibile per '{index_name}': file indice vuoto o mancante. "
            "Rigenera con `python scripts/download_indices.py --force` e fai commit+push."
        )
        st.stop()

    with st.status(f"Analisi di {len(tickers)} titoli…", expanded=True) as status:
        status.write(f"Indice selezionato: {index_name}")
        if index_name == ALL_INDICES:
            status.write(f"Unione indici: {gross} costituenti lordi → {len(tickers)} unici (duplicati rimossi)")
        df, diagnostics = screening(tickers, log=status.write)
        st.session_state["screening_result"] = df
        st.session_state["screening_diagnostics"] = diagnostics
        if diagnostics["valid"] > 0:
            status.update(label=f"Screening completato: {diagnostics['valid']} titoli validi",
                          state="complete")
        else:
            status.update(label="Screening completato senza dati validi", state="error")

df = st.session_state.get("screening_result")
diagnostics = st.session_state.get("screening_diagnostics")
per_index = st.session_state.get("screening_per_index")
gross = st.session_state.get("screening_gross")

if df is None or df.empty:
    if diagnostics and diagnostics.get("total", 0) > 0:
        st.error(
            f"Download dati fallito: {diagnostics['total']} ticker richiesti, 0 validi. "
            "Riprova più tardi (yfinance potrebbe aver limitato le richieste)."
        )
    else:
        st.info("Nessun risultato in memoria. Avvia lo screening.")
    st.stop()

# ── Diagnostica conteggi ───────────────────────────────────
if per_index:
    detail = " · ".join(f"{k}: {v}" for k, v in sorted(per_index.items()))
    st.caption(f"Costituenti per indice → {detail}")

if diagnostics:
    unici = diagnostics["total"]
    lordi = gross if gross is not None else unici
    duplicati = max(0, lordi - unici)

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Costituenti lordi", lordi)
    m2.metric("Titoli unici", unici)
    m3.metric("Duplicati tra indici", duplicati)
    m4.metric("Titoli validi", diagnostics["valid"])
    m5.metric("Scartati download", diagnostics["discarded"])

    if duplicati > 0:
        st.caption(
            "I 'duplicati tra indici' sono titoli presenti in più indici "
            "(es. AAPL in SP500 e NASDAQ100): nello screening unificato "
            "vengono analizzati una sola volta."
        )

# ── Filtri: alert è sottoinsieme di "in sconto" ────────────
discount = df[df["DD%"] <= -20].copy()
alert = df[(df["DD%"] <= -20) & (df["Prezzo"] <= df["VWAP60"])].copy()

# ── Ordinamento esplicito ──────────────────────────────────
sc1, sc2 = st.columns([2, 1])
sort_col = sc1.selectbox(
    "Ordina per",
    ["Bottom", "DD%", "RSI", "Health", "Prezzo", "VWAP60", "Ticker"],
    index=0,
)
sort_dir = sc2.radio("Direzione", ["Discendente", "Ascendente"], horizontal=True)
ascending = sort_dir == "Ascendente"

df_sorted = df.sort_values(sort_col, ascending=ascending).reset_index(drop=True)
discount_sorted = discount.sort_values(sort_col, ascending=ascending).reset_index(drop=True)
alert_sorted = alert.sort_values(sort_col, ascending=ascending).reset_index(drop=True)

tab1, tab2, tab3 = st.tabs([
    f"Tutti ({len(df_sorted)})",
    f"In sconto ({len(discount_sorted)})",
    f"Alert POC/VWAP ({len(alert_sorted)})",
])
with tab1:
    st.dataframe(df_sorted, use_container_width=True, hide_index=True)
with tab2:
    st.dataframe(discount_sorted, use_container_width=True, hide_index=True)
with tab3:
    st.dataframe(alert_sorted, use_container_width=True, hide_index=True)

# ── Analisi di decelerazione ───────────────────────────────
st.markdown("### Analisi di decelerazione")
sel = st.selectbox("Titolo dai risultati", df_sorted["Ticker"].tolist())

try:
    full = get_prices(sel)
except Exception as e:
    st.error(f"Dati non disponibili per {sel}: {e}")
    st.stop()

price = float(full["Close"].iloc[-1])
poc, lo, hi = poc_zone_from_profile(full)
vwap = vwap_anchored(full)
bs = bottom_score(full, poc=poc)

col = COLORS["dark"] if st.session_state.dark_mode else COLORS["light"]
fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                    row_heights=[0.7, 0.3], vertical_spacing=0.03)
fig.add_trace(go.Scatter(x=full.index, y=full["Close"], name="Close",
                         line=dict(color=col["accent"], width=1.5)), 1, 1)
fig.add_hrect(y0=lo, y1=hi, fillcolor=col["warning"], opacity=0.15,
              line_width=0, annotation_text="Zona POC (volume profile)", row=1, col=1)
fig.add_hline(y=poc, line_color=col["text"], line_dash="dash",
              annotation_text="POC", row=1, col=1)
fig.add_hline(y=vwap, line_color=col["text_muted"], line_dash="dot",
              annotation_text="VWAP", row=1, col=1)
roc = full["Close"].pct_change(10) * 100
fig.add_trace(go.Bar(x=full.index, y=roc, name="ROC 10g",
                     marker_color=[col["negative"] if v < 0 else col["positive"]
                                   for v in roc]), 2, 1)
style_fig(fig, st.session_state.dark_mode, height=520)
st.plotly_chart(fig, use_container_width=True)

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Bottom Score", f"{bs['score']}/100")
m2.metric("Drawdown", f"{bs['drawdown']:.1f}%")
m3.metric("RSI", f"{bs['rsi']:.0f}")
m4.metric("ROC 10g", f"{bs['roc10']:+.1f}%")
m5.metric("Decelerazione", f"{bs['decel']:+.1f}")

if bs["score"] >= 70:
    st.success(f"**Operazione Potenziale** — sconto profondo e discesa in decelerazione. {sel} nella zona di accumulo.")
elif bs["score"] >= 50:
    st.warning(f"**Da osservare** — {sel} mostra elementi parziali; attendi conferma dalla zona POC.")
else:
    st.info(f"**Nessun setup** — {sel} non soddisfa i criteri di sconto/decelerazione.")

in_wl = any(e["ticker"] == sel for e in load_watchlist())
if not in_wl:
    if st.button(f"➕ Promuovi {sel} in watchlist (🤖 auto)", type="primary"):
        add_entry(sel, origin="auto", poc=poc)
        st.success(f"{sel} promosso in watchlist come 🤖")
else:
    st.caption(f"{sel} è già in watchlist.")
