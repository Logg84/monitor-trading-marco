"""
Screening: titoli in sconto + alert POC/VWAP + grafico di decelerazione.
Usa volume profile reale.
"""
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

st.set_page_config(page_title="Screening", page_icon="🎛️", layout="wide")

from ui.theme import inject_css, COLORS
from ui.nav import render_navbar, sidebar_nav
from core.data_engine import (
    INDICES_DIR, load_index_constituents, screening,
    get_prices, atr, vwap_anchored, poc_zone_from_profile, bottom_score,
)
from core.watchlist_io import add_entry, load_watchlist

if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = True

inject_css(dark=st.session_state.dark_mode)
render_navbar(title="Screening")
sidebar_nav()

st.markdown("## Screening")
st.caption("Lettura, mai ordine — non è consulenza.")

# Costruisci lista indici disponibili (senza SAMPLE)
available = []
if INDICES_DIR.exists():
    available = sorted(p.stem for p in INDICES_DIR.glob("*.csv"))

# Aggiungi opzione speciale "VISUALIZZA TUTTI INSIEME"
ALL_INDICES = "📊 VISUALIZZA TUTTI INSIEME"
available_with_all = [ALL_INDICES] + available

c1, c2 = st.columns([3, 1])
index_name = c1.selectbox("Indice", available_with_all)
run = c2.button("🚀 Avvia screening", type="primary")

if run:
    if index_name == ALL_INDICES:
        # Unione deduplicata di tutti gli indici
        tickers = []
        for idx_name in available:
            tickers.extend(load_index_constituents(idx_name))
        tickers = sorted(set(tickers))
        st.info(f"Screening unificato: {len(tickers)} ticker unici da {len(available)} indici")
    else:
        tickers = load_index_constituents(index_name)
    
    with st.spinner(f"Analisi di {len(tickers)} titoli…"):
        df, diagnostics = screening(tickers)
        st.session_state["screening_result"] = df
        st.session_state["screening_diagnostics"] = diagnostics

df = st.session_state.get("screening_result")
diagnostics = st.session_state.get("screening_diagnostics")

if df is None or df.empty:
    st.info("Nessun risultato in memoria. Avvia lo screening.")
    st.stop()

# Mostra diagnostica
if diagnostics:
    col1, col2, col3 = st.columns(3)
    col1.metric("Titoli indice", diagnostics["total"])
    col2.metric("Titoli validi", diagnostics["valid"])
    col3.metric("Titoli scartati", diagnostics["discarded"])

# Filtri: alert è sottoinsieme di discount
discount = df[df["DD%"] <= -20].copy()
alert = df[(df["DD%"] <= -20) & (df["Prezzo"] <= df["VWAP60"])].copy()

tab1, tab2, tab3 = st.tabs([
    f"Tutti ({len(df)})", 
    f"In sconto ({len(discount)})", 
    f"Alert POC/VWAP ({len(alert)})"
])

# Controlli ordinamento
sort_col = st.selectbox(
    "Ordina per",
    ["Bottom", "DD%", "RSI", "Health", "Prezzo", "VWAP60", "Ticker"],
    index=0,
    key="sort_col"
)
sort_dir = st.radio("Direzione", ["Discendente", "Ascendente"], horizontal=True, key="sort_dir")

df_sorted = df.sort_values(
    sort_col, 
    ascending=(sort_dir == "Ascendente")
).reset_index(drop=True)

discount_sorted = discount.sort_values(
    sort_col, 
    ascending=(sort_dir == "Ascendente")
).reset_index(drop=True)

alert_sorted = alert.sort_values(
    sort_col, 
    ascending=(sort_dir == "Ascendente")
).reset_index(drop=True)

with tab1:
    st.dataframe(df_sorted, use_container_width=True, hide_index=True)
with tab2:
    st.dataframe(discount_sorted, use_container_width=True, hide_index=True)
with tab3:
    st.dataframe(alert_sorted, use_container_width=True, hide_index=True)

st.markdown("### Analisi di decelerazione")
sel = st.selectbox("Titolo dai risultati", df["Ticker"].tolist())

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
fig.update_layout(
    template="plotly_dark" if st.session_state.dark_mode else "plotly_white",
    paper_bgcolor=col["surface"], plot_bgcolor=col["surface"],
    font=dict(color=col["text"], family="JetBrains Mono"),
    margin=dict(l=10, r=10, t=20, b=10), height=520, showlegend=False,
)
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
    if st.button(f"➕ Promuovi {sel} in watchlist (🤖 auto)"):
        add_entry(sel, origin="auto", poc=poc)
        st.success(f"{sel} promosso in watchlist come 🤖")
else:
    st.caption(f"{sel} è già in watchlist.")
