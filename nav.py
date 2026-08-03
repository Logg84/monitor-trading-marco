import streamlit as st

_NAV_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap');

section[data-testid="stSidebarNav"] { display: none !important; }

.argo-nav-brand { display: flex; align-items: center; gap: 10px; padding: 4px 0 2px 0; }
.argo-nav-brand .logo-mark {
    font-family: 'IBM Plex Mono', monospace; font-weight: 700; font-size: 13px;
    color: #06121f; background: linear-gradient(135deg, #38bdf8, #22d3ee);
    width: 30px; height: 30px; border-radius: 8px; display: inline-flex;
    align-items: center; justify-content: center; letter-spacing: -0.04em;
    box-shadow: 0 6px 18px -8px rgba(56,189,248,.8);
}
.argo-nav-brand .logo-txt {
    font-family: 'Space Grotesk', sans-serif; font-weight: 700; font-size: 17px;
    letter-spacing: -0.02em; color: #f1f5f9; line-height: 1;
}
.argo-nav-brand .logo-txt span { color: #64748b; font-weight: 500; }

div[data-testid="stPageLink"] { width: 100%; }
div[data-testid="stPageLink"] > a, div[data-testid="stPageLink"] > div > a {
    display: flex !important; align-items: center; justify-content: center;
    width: 100%; padding: 9px 8px !important; border-radius: 10px !important;
    border: 1px solid #2a3550 !important; background: rgba(15,23,42,.6) !important;
    color: #94a3b8 !important; text-decoration: none !important;
    font-family: 'Space Grotesk', sans-serif !important; font-weight: 600 !important;
    font-size: 13px !important; letter-spacing: .01em !important;
    transition: transform .15s ease, border-color .2s ease, color .2s ease,
                background .2s ease, box-shadow .2s ease !important;
}
div[data-testid="stPageLink"] > a:hover, div[data-testid="stPageLink"] > div > a:hover {
    transform: translateY(-2px); border-color: #38bdf8 !important; color: #e2e8f0 !important;
    box-shadow: 0 8px 22px -14px rgba(56,189,248,.9);
}
div[data-testid="stPageLink"] svg { display: none !important; }
div[data-testid="stPageLink"] p { margin: 0 !important; color: inherit !important;
    font-family: inherit !important; font-weight: inherit !important; font-size: inherit !important; }

div[data-testid="stPageLink"] a[aria-disabled="true"],
div[data-testid="stPageLink"][aria-disabled="true"] a,
div[data-testid="stPageLink"] a[disabled],
div[data-testid="stPageLink"] > a[tabindex="-1"] {
    background: linear-gradient(135deg, #38bdf8, #0ea5e9) !important;
    border-color: #38bdf8 !important; color: #04121f !important;
    box-shadow: 0 10px 26px -12px rgba(56,189,248,.95) !important;
    pointer-events: none !important; transform: none !important;
}

.argo-eyebrow { font-family: 'IBM Plex Mono', monospace; font-size: 10.5px; font-weight: 600;
    letter-spacing: .18em; text-transform: uppercase; color: #38bdf8; margin: 2px 0 2px 0; }
.argo-viewtitle { font-family: 'Space Grotesk', sans-serif; font-size: 1.5rem; font-weight: 700;
    letter-spacing: -0.02em; color: #f8fafc; margin: 0 0 .4rem 0; }
</style>
"""

def _hide_sidebar_css():
    return '<style>section[data-testid="stSidebar"], [data-testid="stCollapsedControl"]{display:none !important;}</style>'

def render_navbar(current: str, hide_sidebar: bool = False):
    st.markdown(_NAV_CSS, unsafe_allow_html=True)
    if hide_sidebar:
        st.markdown(_hide_sidebar_css(), unsafe_allow_html=True)
    brand, p_w, p_s, p_r, p_c = st.columns([5, 1.4, 1.4, 1.4, 1.4], gap="small")
    with brand:
        st.markdown(
            '<div class="argo-nav-brand"><span class="logo-mark">A</span>'
            '<span class="logo-txt">ARGO <span>× Metodo Rea</span></span></div>',
            unsafe_allow_html=True)
    items = [
        (p_w, "watchlist", "app.py", "📊 Watchlist"),
        (p_s, "screening", "pages/2_Screening.py", "🎛️ Screening"),
        (p_r, "regime", "pages/3_Regime.py", "🧭 Regime"),
        (p_c, "cot", "pages/4_COT.py", "🛢️ COT"),
    ]
    for col, key, path, label in items:
        with col:
            st.page_link(page=path, label=label, use_container_width=True, disabled=(key == current))

def section_header(eyebrow: str, title: str):
    st.markdown(f'<div class="argo-eyebrow">{eyebrow}</div>', unsafe_allow_html=True)
    st.markdown(f'<h1 class="argo-viewtitle">{title}</h1>', unsafe_allow_html=True)
