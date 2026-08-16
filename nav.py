import streamlit as st

_NAV_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700;800&family=IBM+Plex+Mono:wght@500;600;700&family=Inter:wght@500;600;700&display=swap');

:root {
  --bg-base: #0a0f1a;
  --bg-panel: #0f172a;
  --bg-panel-2: #111827;
  --border: #1e293b;
  --border-strong: #334155;
  --txt-1: #f8fafc;
  --txt-2: #cbd5e1;
  --txt-3: #94a3b8;
  --txt-muted: #64748b;
  --accent: #38bdf8;
  --accent-2: #0ea5e9;
  --green: #22c55e;
  --yellow: #f59e0b;
  --red: #ef4444;
  --violet: #a78bfa;
  --cyan: #06b6d4;
}

/* Nascondi la sidebar-nav nativa di Streamlit */
section[data-testid="stSidebarNav"] { display: none !important; }

/* === Brand logo === */
.argo-nav-brand {
  display: flex; align-items: center; gap: 10px;
  padding: 4px 0 2px 0;
  cursor: default;
}
.argo-nav-brand .logo-mark {
  font-family: 'IBM Plex Mono', monospace; font-weight: 700; font-size: 14px;
  color: #04121f;
  background: linear-gradient(135deg, #38bdf8 0%, #06b6d4 50%, #22c55e 100%);
  width: 32px; height: 32px; border-radius: 9px;
  display: inline-flex; align-items: center; justify-content: center;
  letter-spacing: -0.04em;
  box-shadow: 0 8px 22px -10px rgba(56,189,248,.7), inset 0 1px 0 rgba(255,255,255,.2);
  transition: transform .2s ease, box-shadow .2s ease;
}
.argo-nav-brand:hover .logo-mark {
  transform: rotate(-3deg) scale(1.05);
  box-shadow: 0 10px 26px -10px rgba(56,189,248,.9), inset 0 1px 0 rgba(255,255,255,.3);
}
.argo-nav-brand .logo-txt {
  font-family: 'Space Grotesk', sans-serif; font-weight: 800; font-size: 17px;
  letter-spacing: -0.025em; color: var(--txt-1); line-height: 1;
}
.argo-nav-brand .logo-txt span {
  color: var(--txt-muted); font-weight: 500; font-size: 13px;
  letter-spacing: 0;
}

/* === Pills di navigazione === */
div[data-testid="stPageLink"] { width: 100%; }
div[data-testid="stPageLink"] > a, div[data-testid="stPageLink"] > div > a {
  display: flex !important; align-items: center; justify-content: center;
  gap: 4px;
  width: 100%; padding: 9px 10px !important; border-radius: 10px !important;
  border: 1px solid var(--border-strong) !important;
  background: rgba(15, 23, 42, 0.65) !important;
  color: var(--txt-3) !important; text-decoration: none !important;
  font-family: 'Space Grotesk', sans-serif !important; font-weight: 600 !important;
  font-size: 13px !important; letter-spacing: .01em !important;
  transition: transform .15s ease, border-color .2s ease, color .2s ease,
              background .2s ease, box-shadow .2s ease !important;
  position: relative;
}
div[data-testid="stPageLink"] > a:hover, div[data-testid="stPageLink"] > div > a:hover {
  transform: translateY(-2px);
  border-color: var(--accent) !important;
  color: var(--txt-1) !important;
  background: rgba(56, 189, 248, 0.08) !important;
  box-shadow: 0 8px 22px -14px rgba(56,189,248,.7);
}
div[data-testid="stPageLink"] svg { display: none !important; }
div[data-testid="stPageLink"] p {
  margin: 0 !important; color: inherit !important;
  font-family: inherit !important; font-weight: inherit !important; font-size: inherit !important;
}

/* Pill attiva */
div[data-testid="stPageLink"] a[aria-disabled="true"],
div[data-testid="stPageLink"][aria-disabled="true"] a,
div[data-testid="stPageLink"] a[disabled],
div[data-testid="stPageLink"] > a[tabindex="-1"] {
  background: linear-gradient(135deg, #38bdf8, #0ea5e9) !important;
  border-color: var(--accent) !important;
  color: #04121f !important;
  font-weight: 700 !important;
  box-shadow: 0 10px 26px -12px rgba(56,189,248,.8), inset 0 1px 0 rgba(255,255,255,.15) !important;
  pointer-events: none !important;
  transform: none !important;
}

/* === Chip regime dinamico === */
.argo-regime-chip {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 7px 13px;
  background: rgba(15, 23, 42, 0.75);
  border: 1px solid var(--border-strong);
  border-radius: 10px;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--txt-2);
  cursor: default;
  transition: transform .15s ease, border-color .2s ease, box-shadow .2s ease;
  white-space: nowrap;
}
.argo-regime-chip:hover {
  transform: translateY(-1px);
  border-color: var(--accent);
  box-shadow: 0 6px 18px -10px rgba(56,189,248,.6);
}
.argo-regime-chip .dot {
  width: 9px; height: 9px; border-radius: 50%;
  box-shadow: 0 0 10px currentColor;
  animation: regime-pulse 2.4s ease-in-out infinite;
}
.argo-regime-chip .label {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 9px;
  color: var(--txt-muted);
  text-transform: uppercase;
  letter-spacing: .1em;
}
.argo-regime-chip .bias {
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 800;
  font-size: 12px;
  letter-spacing: 0.02em;
}
@keyframes regime-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.55; transform: scale(0.88); }
}

/* === Section header === */
.argo-eyebrow {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10.5px; font-weight: 600;
  letter-spacing: .18em; text-transform: uppercase;
  color: var(--accent);
  margin: 8px 0 4px 0;
  display: inline-block;
  padding: 2px 9px;
  background: rgba(56, 189, 248, 0.08);
  border: 1px solid rgba(56, 189, 248, 0.25);
  border-radius: 6px;
}
.argo-viewtitle {
  font-family: 'Space Grotesk', sans-serif;
  font-size: 1.7rem; font-weight: 800;
  letter-spacing: -0.025em;
  color: var(--txt-1);
  margin: 0 0 .6rem 0;
  line-height: 1.1;
}

/* Mobile: stack pills su schermi piccoli */
@media (max-width: 768px) {
  div[data-testid="stPageLink"] > a, div[data-testid="stPageLink"] > div > a {
    font-size: 11px !important; padding: 7px 5px !important;
  }
  .argo-regime-chip { font-size: 10px; padding: 5px 9px; }
  .argo-regime-chip .bias { font-size: 11px; }
  .argo-viewtitle { font-size: 1.35rem; }
}
</style>
"""

_REGIME_COLORS = {
    "emerald": ("#10b981", "LONG"),
    "rose":    ("#f43f5e", "SHORT"),
    "amber":   ("#f59e0b", "NEUTRO"),
    "indigo":  ("#6366f1", "LONG"),
    "orange":  ("#f97316", "SHORT"),
    "slate":   ("#64748b", "NEUTRO"),
}


def _hide_sidebar_css():
    return '<style>section[data-testid="stSidebar"], [data-testid="stCollapsedControl"]{display:none !important;}</style>'


def render_navbar(current: str, hide_sidebar: bool = False, bussola: dict | None = None):
    """
    Render della navbar globale ARGO.

    Parametri:
    - current:       chiave della pagina attiva (watchlist|screening|regime|cot)
    - hide_sidebar:  se True, nasconde sidebar Streamlit (usato in COT/Regime)
    - bussola:       dict opzionale con chiavi 'color', 'bias', 'stato', 'rapporto'
                     per mostrare il chip Regime in tempo reale.
    """
    st.markdown(_NAV_CSS, unsafe_allow_html=True)
    if hide_sidebar:
        st.markdown(_hide_sidebar_css(), unsafe_allow_html=True)

    # Colonne: brand | 4 pills | regime chip
    brand, p_w, p_s, p_r, p_c, p_regime = st.columns([4.5, 1.3, 1.3, 1.3, 1.3, 1.6], gap="small")

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
        (p_c, "cot", "pages/4_COT.py", "🛢️ COT"),
    ]
    for col, key, path, label in items:
        with col:
            st.page_link(page=path, label=label, use_container_width=True, disabled=(key == current))

    # Chip regime (se fornito dalla pagina chiamante)
    with p_regime:
        if bussola and isinstance(bussola, dict):
            color_hex = _REGIME_COLORS.get(bussola.get("color", "slate"), ("#64748b", "NEUTRO"))[0]
            bias = str(bussola.get("bias", "N/D")).upper()
            stato = str(bussola.get("stato", "")).upper()
            rapporto = bussola.get("rapporto")
            title = f"Stato: {stato} | Bias: {bias}"
            if rapporto is not None:
                try:
                    title += f" | VVIX/VIX: {float(rapporto):.2f}"
                except Exception:
                    pass
            st.markdown(
                f'<div class="argo-regime-chip" title="{title}" style="color:{color_hex}">'
                f'<span class="dot" style="background:{color_hex}"></span>'
                f'<span class="label">Regime</span>'
                f'<span class="bias">{bias}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="argo-regime-chip" title="Caricamento Bussola...">'
                '<span class="dot" style="background:#64748b"></span>'
                '<span class="label">Regime</span>'
                '<span class="bias">—</span>'
                '</div>',
                unsafe_allow_html=True,
            )


def section_header(eyebrow: str, title: str, subtitle: str = ""):
    """Eyebrow + titolo sezione. Opzionale: subtitle descrittivo."""
    st.markdown(f'<div class="argo-eyebrow">{eyebrow}</div>', unsafe_allow_html=True)
    st.markdown(f'<h1 class="argo-viewtitle">{title}</h1>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(
            f'<p style="color:var(--txt-3);font-size:13px;margin-top:-4px;margin-bottom:18px;'
            f'font-family:\'Inter\',sans-serif;line-height:1.5">{subtitle}</p>',
            unsafe_allow_html=True,
        )
