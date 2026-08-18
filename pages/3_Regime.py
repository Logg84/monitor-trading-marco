"""
Regime — Bussola: 6 attori, gauge composite, SPX con flip-line e ±2σ,
termometro VIX/VVIX.
"""
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np

st.set_page_config(page_title="Regime", page_icon="🧭", layout="wide")

from ui.theme import inject_css, COLORS
from ui.nav import render_navbar, sidebar_nav
from core.regime import compute_regime
from core.data_engine import get_prices

if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = True

inject_css(dark=st.session_state.dark_mode)
render_navbar(title="Regime")
sidebar_nav()


def _rgba(hex_color: str, alpha: float) -> str:
    """#RRGGBB → rgba(r,g,b,a). Plotly accetta questo formato ovunque."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha:.3f})"


st.markdown("## Regime — Bussola")
st.caption("Il bias modula la size suggerita: ×0.3 SHORT · ×0.6 NEUTRO · ×1.0 LONG. La decisione resta tua.")

with st.spinner("Calcolo attori di mercato…"):
    reg = compute_regime()

col = COLORS["dark"] if st.session_state.dark_mode else COLORS["light"]

# ── Gauge composite ────────────────────────────────────────
g1, g2 = st.columns([2, 1])
with g1:
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=round(reg["composite"], 1),
        number={"font": {"size": 30, "color": col["text"]}},
        gauge={
            "axis": {"range": [-100, 100], "tickcolor": col["text_muted"],
                     "tickfont": {"color": col["text_muted"]}},
            "bar": {"color": col["accent"], "thickness": 0.3},
            "bgcolor": col["surface"],
            "bordercolor": col["border"],
            "steps": [
                {"range": [-100, -15], "color": _rgba(col["negative"], 0.2)},
                {"range": [-15, 15],   "color": _rgba(col["warning"],  0.2)},
                {"range": [15, 100],   "color": _rgba(col["positive"], 0.2)},
            ],
        },
    ))
    fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=260,
                      paper_bgcolor=col["surface"])
    st.plotly_chart(fig, use_container_width=True)

with g2:
    st.metric("Regime", reg["regime"])
    st.metric("Composite", f"{reg['composite']:+.1f}")
    st.caption("Attori COT assenti → pesi rinormalizzati sugli attori con dati.")

# ── Tabella attori ─────────────────────────────────────────
st.markdown("### Attori di mercato")
rows = []
for a in reg["actors"]:
    rows.append({
        "Attore": a["name"],
        "Score": round(a["score"], 0),
        "Fonte": a["source"],
        "Dettaglio": a["detail"],
    })
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ── SPX con flip-line e ±2σ ────────────────────────────────
st.markdown("### SPX — flip-line e barriere ±2σ")
try:
    spx = get_prices("^GSPC")
    close = spx["Close"]
    sma200 = close.rolling(200).mean()
    sma20 = close.rolling(20).mean()
    sd2 = close.rolling(20).std() * 2

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=close.index, y=close, name="SPX",
                             line=dict(color=col["accent"], width=1.5)))
    fig.add_trace(go.Scatter(x=close.index, y=sma200, name="SMA200 (flip-line)",
                             line=dict(color=col["text"], width=1, dash="dash")))
    fig.add_trace(go.Scatter(x=close.index, y=sma20 + sd2, name="+2σ",
                             line=dict(color=col["negative"], width=1, dash="dot")))
    fig.add_trace(go.Scatter(x=close.index, y=sma20 - sd2, name="-2σ",
                             line=dict(color=col["positive"], width=1, dash="dot"),
                             fill="tonexty",
                             fillcolor=_rgba(col["positive"], 0.07)))
    fig.update_layout(
        template="plotly_dark" if st.session_state.dark_mode else "plotly_white",
        paper_bgcolor=col["surface"], plot_bgcolor=col["surface"],
        font=dict(color=col["text"], family="Inter"),
        margin=dict(l=10, r=10, t=20, b=10), height=420, showlegend=True,
        legend=dict(orientation="h", y=1.08),
    )
    st.plotly_chart(fig, use_container_width=True)
except Exception as e:
    st.error(f"SPX non disponibile: {e}")

# ── Termometro volatilità ──────────────────────────────────
st.markdown("### Termometro volatilità")
try:
    vix = get_prices("^VIX")["Close"]
    vvix = get_prices("^VVIX")["Close"]
    v_level = float(vix.iloc[-1])
    ratio = float(vvix.iloc[-1]) / v_level if v_level > 0 else float("nan")
    t1, t2, t3 = st.columns(3)
    t1.metric("VIX", f"{v_level:.1f}",
              "paura" if v_level > 25 else ("compiacenza" if v_level < 15 else "normale"))
    t2.metric("VVIX/VIX", f"{ratio:.2f}")
    t3.metric("Pendenza VIX 1M", f"{float(vix.iloc[-1] - vix.iloc[-21]):+.1f}")
except Exception as e:
    st.error(f"Dati volatilità non disponibili: {e}")

st.caption("Lettura contrarian per operatore medio-lungo: paura estrema = opportunità di accumulo; euforia = rischio.")