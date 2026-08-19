"""
Navbar con chip regime live + navigazione.
"""
import streamlit as st

REGIME_LABELS = {
    "LONG":    ("🟢 LONG",    "long"),
    "NEUTRO":  ("🟡 NEUTRO",  "neutral"),
    "SHORT":   ("🔴 SHORT",   "short"),
}

def _live_regime() -> str:
    try:
        from core.regime import compute_regime
        return compute_regime()["regime"]
    except Exception:
        return "NEUTRO"

def render_navbar(regime: str | None = None, title: str = "Terminale") -> None:
    regime = regime or _live_regime()
    label, cls = REGIME_LABELS.get(regime.upper(), REGIME_LABELS["NEUTRO"])
    st.markdown(
        f"""
        <div class="argo-nav">
            <span class="argo-nav-title">📊 {title}</span>
            <span class="argo-chip {cls}">{label}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

def sidebar_nav() -> None:
    with st.sidebar:
        st.markdown("### Navigazione")
        st.page_link("app.py", label="Watchlist", icon="📊")
        st.page_link("pages/2_Screening.py", label="Screening", icon="🎛️")
        st.page_link("pages/3_Regime.py", label="Regime", icon="🧭")
        st.page_link("pages/4_COT.py", label="COT", icon="🛢️")
        st.markdown("---")
        st.caption("Lettura, mai ordine — non è consulenza")