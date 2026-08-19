"""
Screening: titoli in sconto + zone volumetriche + VWAP ancorati + segnale +
grafico di decelerazione. Log di avanzamento per le operazioni lunghe.
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
    get_prices, get_prices_long, vwap_anchored,
    volume_zones, structural_anchors, bottom_score,
)
from core.watchlist_io import add_entry, load_watchlist

if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = True

inject_css(dark=st.session_state.dark_mode)
render_navbar(title="Screening")
sidebar_nav()

st.markdown("## Screening")
st.caption("Lettura, mai ordine — non è consulenza.")

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
            status.write(f"Unione indici: {gross} lordi → {len(tickers)} unici")
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

st.caption(
    "Zone volumetriche su settimanale lungo: score = 60% dimensione + 40% recency (half-life 4y). "
    "VWA1-3: VWAP ancorati a minimi strutturali; nello screening senza bonus trimestrale (prestazioni). "
    "Segnale 🟢 = DD≤−20% + decel>0 + RSI<45 + (in zona o ≤VWA1). Lettura, mai ordine."
)

discount = df[df["DD%"] <= -20].copy()
alert = df[(df["DD%"] <= -20) & (df["Prezzo"] <= df["VWAP60"])].copy()

sc1, sc2 = st.columns([2, 1])
sort_col = sc1.selectbox(
    "Ordina per",
    ["Bottom", "DD%", "RSI", "Health", "Prezzo", "VWAP60", "VWA1", "Ticker"],
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

try:
    wdf = get_prices_long(sel)
except Exception:
    wdf = full
zones = volume_zones(wdf)
anchors = structural_anchors(wdf)
vwap60 = vwap_anchored(full)
bs = bottom_score(full, zones=zones)

price = float(full["Close"].iloc[-1])
col = COLORS["dark"] if st.session_state.dark_mode else COLORS["light"]
fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                    row_heights=[0.7, 0.3], vertical_spacing=0.03)
fig.add_trace(go.Scatter(x=full.index, y=full["Close"], name="Close",
                         line=dict(color=col["accent"], width=1.5)), 1, 1)
ylo = float(full["Low"].min()) * 0.97
yhi = float(full["High"].max()) * 1.03
for zi, z in enumerate(zones[:3], 1):
    if z["hi"] < ylo or z["lo"] > yhi:
        continue
    fig.add_hrect(y0=z["lo"], y1=z["hi"], fillcolor=col["warning"],
                  opacity=0.08 + 0.20 * z["score"] / 100,
                  line_width=0, annotation_text=f"Z{zi} ·{z['score']}",
                  row=1, col=1)
for an in anchors:
    if ylo <= an["vwap"] <= yhi:
        fig.add_hline(y=an["vwap"], line_color=col["positive"], line_dash="dot",
                      annotation_text=f"{an['label']} {an['date'].strftime('%m/%y')}",
                      row=1, col=1)
fig.add_hline(y=vwap60, line_color=col["text_muted"], line_dash="dot",
              annotation_text="VWAP60", row=1, col=1)
fig.update_yaxes(range=[ylo, yhi], row=1, col=1)
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
    st.success(f"**Operazione Potenziale** — sconto profondo e discesa in decelerazione. {sel} a ridosso di una zona volumetrica.")
elif bs["score"] >= 50:
    st.warning(f"**Da osservare** — {sel} mostra elementi parziali; attendi conferma dalla zona.")
else:
    st.info(f"**Nessun setup** — {sel} non soddisfa i criteri di sconto/decelerazione.")

in_wl = any(e["ticker"] == sel for e in load_watchlist())
if not in_wl:
    if st.button(f"➕ Promuovi {sel} in watchlist (🤖 auto)", type="primary"):
        add_entry(sel, origin="auto",
                  poc=zones[0]["center"] if zones else None)
        st.success(f"{sel} promosso in watchlist come 🤖")
else:
    st.caption(f"{sel} è già in watchlist.")
