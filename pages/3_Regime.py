"""
Regime — Bussola: 6 attori con sfondi colorati a intensità proporzionale
allo score, gauge composite, SPX con flip-line e ±2σ, termometro VIX/VVIX.
"""
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="Regime", page_icon="🧭", layout="wide")

from ui.theme import inject_css, COLORS, FONT_MONO, style_fig
from ui.nav import render_navbar, sidebar_nav
from core.regime import compute_regime
from core.data_engine import get_prices

if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = True

inject_css(dark=st.session_state.dark_mode)
render_navbar(title="Regime")
sidebar_nav()

def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha:.3f})"

def score_bg(score: float, col: dict, max_alpha: float = 0.55) -> str:
    """Verde se positivo, rosso se negativo; alpha ∝ |score|."""
    s = max(-100.0, min(100.0, float(score)))
    alpha = abs(s) / 100 * max_alpha
    base = col["positive"] if s >= 0 else col["negative"]
    return _rgba(base, alpha)

col = COLORS["dark"] if st.session_state.dark_mode else COLORS["light"]

st.markdown("## Regime — Bussola")
st.caption("Il bias modula la size suggerita: ×0.3 SHORT · ×0.6 NEUTRO · ×1.0 LONG. La decisione resta tua.")

with st.spinner("Calcolo attori di mercato…"):
    reg = compute_regime()

# ── Gauge + regime ─────────────────────────────────────────
g1, g2 = st.columns([2, 1])
with g1:
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=round(reg["composite"], 1),
        number={"font": {"size": 30, "color": col["text"], "family": FONT_MONO}},
        gauge={
            "axis": {"range": [-100, 100], "tickcolor": col["text_muted"],
                     "tickfont": {"color": col["text_muted"], "family": FONT_MONO}},
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
    reg_bg = score_bg(reg["composite"], col)
    st.markdown(
        f"""
        <div style="background:{reg_bg}; border:1px solid {col['border']};
             border-radius:4px; padding:20px; text-align:center; margin-bottom:12px;">
            <div style="color:{col['text_muted']}; font-size:12px;">REGIME</div>
            <div style="color:{col['text']}; font-size:28px; font-weight:700;">{reg['regime']}</div>
        </div>
        """, unsafe_allow_html=True)
    st.metric("Composite", f"{reg['composite']:+.1f}")
    st.caption("Attori COT assenti → pesi rinormalizzati sugli attori con dati.")

# ── Tabella attori con sfondi a intensità ──────────────────
st.markdown("### Attori di mercato")
rows_html = ""
for a in reg["actors"]:
    bg = score_bg(a["score"], col)
    rows_html += f"""
    <tr style="background:{bg};">
        <td>{a['name']}</td>
        <td class="num">{a['score']:+.0f}</td>
        <td>{a['source']}</td>
        <td>{a['detail']}</td>
    </tr>"""

st.markdown(
    f"""
    <style>
    table.argo-table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    table.argo-table th {{ text-align:left; color:{col['text_muted']}; font-size:11px;
        text-transform:uppercase; letter-spacing:.05em; padding:8px 12px;
        border-bottom:1px solid {col['border']}; }}
    table.argo-table td {{ padding:10px 12px; border-bottom:1px solid {col['border']};
        color:{col['text']}; }}
    table.argo-table td.num {{ font-family:{FONT_MONO}; font-weight:600; text-align:right; }}
    .kcard {{ border:1px solid {col['border']}; border-radius:4px; padding:16px;
        text-align:center; }}
    .klabel {{ color:{col['text_muted']}; font-size:12px; }}
    .kvalue {{ color:{col['text']}; font-family:{FONT_MONO}; font-size:22px; font-weight:600; }}
    .ksub {{ color:{col['text_muted']}; font-size:11px; }}
    </style>
    <table class="argo-table">
        <thead> <tr> <th>Attore</th> <th>Score</th> <th>Fonte</th> <th>Dettaglio</th> </tr> </thead>
        <tbody>{rows_html}</tbody>
    </table>
    """,
    unsafe_allow_html=True,
)

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
    style_fig(fig, st.session_state.dark_mode, height=420,
              showlegend=True, legend_top=True)
    st.plotly_chart(fig, use_container_width=True)
except Exception as e:
    st.error(f"SPX non disponibile: {e}")

# ── Termometro volatilità con card colorate ────────────────
st.markdown("### Termometro volatilità")
try:
    vix = get_prices("^VIX")["Close"]
    vvix = get_prices("^VVIX")["Close"]
    v_level = float(vix.iloc[-1])
    ratio = float(vvix.iloc[-1]) / v_level if v_level > 0 else float("nan")
    slope = float(vix.iloc[-1] - vix.iloc[-21]) if len(vix) > 21 else 0.0

    # Lettura contrarian: paura = opportunità (verde), compiacenza = rischio (rosso)
    if v_level > 25:
        v_bg, v_sub = score_bg(60, col), "paura → opportunità"
    elif v_level < 15:
        v_bg, v_sub = score_bg(-60, col), "compiacenza → rischio"
    else:
        v_bg, v_sub = _rgba(col["warning"], 0.15), "normale"

    r_bg = score_bg(min(max((ratio - 1.0) * 150, -100), 100), col)
    s_bg = score_bg(-slope * 4, col)

    c1, c2, c3 = st.columns(3)
    c1.markdown(
        f"<div class='kcard' style='background:{v_bg};'><div class='klabel'>VIX</div>"
        f"<div class='kvalue'>{v_level:.1f}</div><div class='ksub'>{v_sub}</div></div>",
        unsafe_allow_html=True)
    c2.markdown(
        f"<div class='kcard' style='background:{r_bg};'><div class='klabel'>VVIX/VIX</div>"
        f"<div class='kvalue'>{ratio:.2f}</div><div class='ksub'>>1.2 stress · <0.9 compiacenza</div></div>",
        unsafe_allow_html=True)
    c3.markdown(
        f"<div class='kcard' style='background:{s_bg};'><div class='klabel'>Pendenza VIX 1M</div>"
        f"<div class='kvalue'>{slope:+.1f}</div><div class='ksub'>calante = panico che rientra</div></div>",
        unsafe_allow_html=True)
except Exception as e:
    st.error(f"Dati volatilità non disponibili: {e}")

st.caption("Lettura contrarian per operatore medio-lungo: paura estrema = opportunità di accumulo; euforia = rischio.")
