"""
Barra di navigazione condivisa tra le tre viste (Watchlist / Screening / Regime).
Sostituisce il menu multipage a scomparsa e i tab: tre pill fissi in alto,
quello della vista corrente evidenziato. Il CSS di sistema (banner regime,
actor-box) vive qui così non è duplicato nelle pagine.
"""
import streamlit as st

_NAV_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap');

/* ---- nascondi il menu multipage nativo (la lista pagine in cima alla sidebar) ---- */
[data-testid="stSidebarNav"] { display: none !important; }

/* ---- barra di navigazione ---- */
.argo-nav-brand {
    display: flex; align-items: center; gap: 10px; padding: 4px 0 2px 0;
}
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

/* ---- pill di navigazione (st.page_link) ---- */
div[data-testid="stPageLink"] { width: 100%; }
div[data-testid="stPageLink"] > a,
div[data-testid="stPageLink"] > div > a {
    display: flex !important; align-items: center; justify-content: center;
    width: 100%; padding: 9px 10px !important; border-radius: 10px !important;
    border: 1px solid #2a3550 !important; background: rgba(15,23,42,.6) !important;
    color: #94a3b8 !important; text-decoration: none !important;
    font-family: 'Space Grotesk', sans-serif !important; font-weight: 600 !important;
    font-size: 13px !important; letter-spacing: 0.01em !important;
    transition: transform .15s ease, border-color .2s ease, color .2s ease,
                background .2s ease, box-shadow .2s ease !important;
}
div[data-testid="stPageLink"] > a:hover,
div[data-testid="stPageLink"] > div > a:hover {
    transform: translateY(-2px); border-color: #38bdf8 !important; color: #e2e8f0 !important;
    box-shadow: 0 8px 22px -14px rgba(56,189,248,.9);
}
/* nascondi freccia/icona di default del page_link */
div[data-testid="stPageLink"] svg { display: none !important; }
div[data-testid="stPageLink"] p { margin: 0 !important; color: inherit !important;
    font-family: inherit !important; font-weight: inherit !important; font-size: inherit !important; }

/* ---- pill ATTIVO (page_link disabilitato = vista corrente) ---- */
div[data-testid="stPageLink"] a[aria-disabled="true"],
div[data-testid="stPageLink"][aria-disabled="true"] a,
div[data-testid="stPageLink"] a[disabled],
div[data-testid="stPageLink"] > a[tabindex="-1"] {
    background: linear-gradient(135deg, #38bdf8, #0ea5e9) !important;
    border-color: #38bdf8 !important; color: #04121f !important;
    box-shadow: 0 10px 26px -12px rgba(56,189,248,.95) !important;
    pointer-events: none !important; transform: none !important;
}

/* ---- banner cambio regime + direttiva tattica (condivisi) ---- */
.state-change-banner {
    padding: 10px 15px; border-radius: 8px; margin-bottom: 15px;
    border-left: 6px solid #fbbf24; background-color: #1e293b;
    border: 1px solid #334155; color: #f8fafc; transition: box-shadow .25s ease;
}
.state-change-banner:hover { box-shadow: 0 6px 22px -10px rgba(251,191,36,.5); }

/* ---- box attori (vista Regime) ---- */
.actor-box {
    background-color: #0f172a; border-radius: 6px; padding: 10px 8px;
    border: 1px solid #334155; text-align: center; height: 100%;
    transition: transform .15s ease, border-color .2s ease;
}
.actor-box:hover { transform: translateY(-2px); border-color: #475569; }
.actor-box .emoji { font-size: 20px; }
.actor-box .label { font-size: 11px; font-weight: bold; color: #94a3b8; margin-top: 2px; }
.actor-box .value { font-size: 16px; font-weight: 800; margin: 2px 0; }
.actor-box .desc { font-size: 10px; color: #cbd5e1; line-height: 1.2; }

/* ---- header di sezione sotto la nav ---- */
.argo-eyebrow {
    font-family: 'IBM Plex Mono', monospace; font-size: 10.5px; font-weight: 600;
    letter-spacing: .18em; text-transform: uppercase; color: #38bdf8; margin: 2px 0 2px 0;
}
.argo-viewtitle {
    font-family: 'Space Grotesk', sans-serif; font-size: 1.5rem; font-weight: 700;
    letter-spacing: -0.02em; color: #f8fafc; margin: 0 0 .4rem 0;
}
</style>
"""


def _hide_sidebar_css() -> str:
    return "<style>section[data-testid=\"stSidebar\"], [data-testid=\"stCollapsedControl\"]{display:none !important;}</style>"


def render_navbar(current: str, hide_sidebar: bool = False):
    """Disegna la barra di navigazione. `current` in {"watchlist","screening","regime"}.
    `hide_sidebar`=True nasconde del tutto la sidebar (pagine senza controlli)."""
    st.markdown(_NAV_CSS, unsafe_allow_html=True)
    if hide_sidebar:
        st.markdown(_hide_sidebar_css(), unsafe_allow_html=True)

    brand, p_w, p_s, p_r = st.columns([5, 1.5, 1.5, 1.5], gap="small")
    with brand:
        st.markdown(
            '<div class="argo-nav-brand">'
            '<span class="logo-mark">A</span>'
            '<span class="logo-txt">ARGO <span>× Metodo Rea</span></span>'
            '</div>',
            unsafe_allow_html=True,
        )
    items = [
        (p_w, "watchlist", "app.py", "📊 Watchlist"),
        (p_s, "screening", "pages/2_Screening.py", "🎛️ Screening"),
        (p_r, "regime", "pages/3_Regime.py", "🧭 Regime"),
    ]
    for col, key, path, label in items:
        with col:
            st.page_link(page=path, label=label, use_container_width=True, disabled=(key == current))


def section_header(eyebrow: str, title: str):
    st.markdown(f'<div class="argo-eyebrow">{eyebrow}</div>', unsafe_allow_html=True)
    st.markdown(f'<h1 class="argo-viewtitle">{title}</h1>', unsafe_allow_html=True)
