"""
Navbar con chip regime live + navigazione alta.
La sidebar resta solo per toggle tema + disclaimer.
"""
import streamlit as st

REGIME_LABELS = {
    "LONG":    ("🟢 LONG",    "long"),
    "NEUTRO":  ("🟡 NEUTRO",  "neutral"),
    "SHORT":   ("🔴 SHORT",   "short"),
}

PAGES = [
    ("app.py",               "Watchlist", "📊"),
    ("pages/2_Screening.py", "Screening", "🎛️"),
    ("pages/3_Regime.py",    "Regime",    "🧭"),
    ("pages/4_COT.py",       "COT",       "🛢️"),
]

def _live_regime() -> str:
    try:
        from core.regime import compute_regime
        return compute_regime()["regime"]
    except Exception:
        return "NEUTRO"

def render_navbar(regime: str | None = None, title: str = "Terminale") -> None:
    """Barra alta: titolo + chip regime + bottoni di navigazione."""
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

    cols = st.columns(len(PAGES), gap="small")
    for c, (path, plabel, icon) in zip(cols, PAGES):
        if plabel == title:
            c.markdown(
                f'<div class="argo-navlink active">{icon} {plabel}</div>',
                unsafe_allow_html=True,
            )
        else:
            c.page_link(path, label=plabel, icon=icon, use_container_width=True)

def sidebar_nav() -> None:
    """Sidebar minimale: toggle tema + disclaimer. Niente duplicati di navigazione."""
    with st.sidebar:
        st.markdown("---")
        label = "☀️ Tema chiaro" if st.session_state.get("dark_mode", True) else "🌙 Tema scuro"
        if st.button(label, use_container_width=True, key="sidebar_theme_toggle"):
            st.session_state.dark_mode = not st.session_state.get("dark_mode", True)
            st.rerun()
        st.caption("Lettura, mai ordine — non è consulenza")
