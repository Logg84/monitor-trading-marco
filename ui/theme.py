"""
Design system — palette ad alto contrasto, zero decorazioni, sostanza.
Sidebar rimossa: navigazione e toggle tema vivono nella navbar alta.
"""
import streamlit as st

# ── Palette ────────────────────────────────────────────────
COLORS = {
    # Dark theme
    "dark": {
        "bg":         "#0D1117",
        "surface":    "#161B22",
        "border":     "#30363D",
        "text":       "#E6EDF3",
        "text_muted": "#8B949E",
        "accent":     "#58A6FF",
        "positive":   "#3FB950",
        "negative":   "#F85149",
        "warning":    "#D29922",
    },
    # Light theme
    "light": {
        "bg":         "#FAFBFC",
        "surface":    "#FFFFFF",
        "border":     "#D0D7DE",
        "text":       "#1F2328",
        "text_muted": "#656D76",
        "accent":     "#0969DA",
        "positive":   "#1A7F37",
        "negative":   "#CF222E",
        "warning":    "#9A6700",
    },
}

FONT_TEXT = "Inter, -apple-system, sans-serif"
FONT_MONO = "'JetBrains Mono', 'Fira Code', monospace"

# ── CSS globale ────────────────────────────────────────────
def inject_css(dark: bool = True) -> None:
    c = COLORS["dark"] if dark else COLORS["light"]
    css = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* Base */
.stApp {{
    background-color: {c['bg']};
    color: {c['text']};
    font-family: {FONT_TEXT};
    font-size: 14px;
}}

/* Sidebar ELIMINATA: nascosta ovunque, insieme alle frecce di collasso */
[data-testid="stSidebar"] {{
    display: none;
}}
[data-testid="stSidebarCollapseButton"] {{
    display: none;
}}
[data-testid="stSidebarCollapsedControl"] {{
    display: none;
}}
[data-testid="stSidebarNav"] {{
    display: none;
}}

/* Header / navbar */
.argo-nav {{
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 12px 24px;
    background: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 4px;
    margin-bottom: 8px;
}}
.argo-nav-title {{
    font-size: 16px;
    font-weight: 700;
    color: {c['text']};
    letter-spacing: 0.02em;
}}
.argo-chip {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 600;
    border: 1px solid {c['border']};
    background: {c['bg']};
    color: {c['text_muted']};
}}
.argo-chip.long {{ border-color: {c['positive']}; color: {c['positive']}; }}
.argo-chip.short {{ border-color: {c['negative']}; color: {c['negative']}; }}
.argo-chip.neutral {{ border-color: {c['warning']}; color: {c['warning']}; }}

/* Navigazione alta: chip-link (page_link) e pagina attiva */
[data-testid="stPageLink"] {{
    margin: 0;
}}
[data-testid="stPageLink"] a {{
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 8px 12px;
    border: 1px solid {c['border']};
    border-radius: 4px;
    background: {c['surface']};
    color: {c['text']};
    font-size: 13px;
    font-weight: 600;
    text-decoration: none;
}}
[data-testid="stPageLink"] a:hover {{
    border-color: {c['accent']};
    color: {c['accent']};
}}
.argo-navlink {{
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 8px 12px;
    border: 1px solid {c['accent']};
    border-radius: 4px;
    background: {c['bg']};
    color: {c['accent']};
    font-size: 13px;
    font-weight: 600;
}}

/* Card / containers */
.argo-card {{
    background: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 4px;
    padding: 24px;
    margin-bottom: 24px;
}}

/* Headings */
h1, h2, h3 {{
    color: {c['text']};
    font-weight: 600;
}}
h1 {{ font-size: 22px; }}
h2 {{ font-size: 18px; }}
h3 {{ font-size: 15px; }}

/* Tables */
[data-testid="stDataFrame"] {{
    font-family: {FONT_MONO};
    font-size: 13px;
}}
[data-testid="stTable"] th {{
    background: {c['bg']};
    color: {c['text_muted']};
    font-weight: 600;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}}

/* Bottoni: gerarchia primary/secondary */
.stButton > button {{
    background: {c['surface']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: 4px;
    padding: 8px 20px;
    font-weight: 600;
    font-size: 13px;
}}
.stButton > button:hover {{
    border-color: {c['accent']};
    color: {c['accent']};
}}
.stButton > button[data-testid="stBaseButton-primary"],
.stButton > button[kind="primary"] {{
    background: {c['accent']};
    color: #FFFFFF;
    border: none;
}}
.stButton > button[data-testid="stBaseButton-primary"]:hover,
.stButton > button[kind="primary"]:hover {{
    opacity: 0.9;
    color: #FFFFFF;
}}

/* Metrics */
[data-testid="stMetric"] {{
    background: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 4px;
    padding: 16px;
}}
[data-testid="stMetricLabel"] {{
    color: {c['text_muted']};
    font-size: 12px;
    font-weight: 500;
}}
[data-testid="stMetricValue"] {{
    font-family: {FONT_MONO};
    font-size: 20px;
    font-weight: 600;
}}

/* Inputs */
.stTextInput input, .stNumberInput input, .stSelectbox select {{
    background: {c['bg']};
    border: 1px solid {c['border']};
    color: {c['text']};
    border-radius: 4px;
}}

/* Radio / checkbox: testo in palette */
[data-testid="stRadio"] label,
[data-testid="stRadio"] div[role="radio"] {{
    color: {c['text']};
    font-size: 13px;
}}
[data-testid="stCheckbox"] label {{
    color: {c['text']};
    font-size: 13px;
}}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {{
    border-bottom: 1px solid {c['border']};
}}
.stTabs [data-baseweb="tab"] {{
    color: {c['text_muted']};
    font-weight: 500;
}}
.stTabs [aria-selected="true"] {{
    color: {c['accent']};
    border-bottom-color: {c['accent']};
}}

/* Alert boxes */
[data-testid="stAlert"] {{
    border-radius: 4px;
    border: 1px solid {c['border']};
}}

/* Container: larghezza TOTALE, padding-top che evita l'header fisso */
.block-container {{
    padding-top: 84px;
    padding-bottom: 24px;
    padding-left: 24px;
    padding-right: 24px;
    max-width: 100%;
}}
</style>
"""
    st.markdown(css, unsafe_allow_html=True)

# ── Helper Plotly ──────────────────────────────────────────
def style_fig(fig, dark: bool, height: int = 420,
              showlegend: bool = False, legend_top: bool = False):
    """
    Stile uniforme per tutti i grafici: sfondi surface, testo Inter,
    numeri assi JetBrains Mono, griglie in palette.
    """
    c = COLORS["dark"] if dark else COLORS["light"]
    fig.update_layout(
        template="plotly_dark" if dark else "plotly_white",
        paper_bgcolor=c["surface"],
        plot_bgcolor=c["surface"],
        font=dict(color=c["text"], family=FONT_TEXT),
        margin=dict(l=10, r=10, t=40 if legend_top else 30, b=10),
        height=height,
        showlegend=showlegend,
    )
    fig.update_xaxes(
        tickfont=dict(family=FONT_MONO, size=11, color=c["text_muted"]),
        gridcolor=c["border"],
        linecolor=c["border"],
    )
    fig.update_yaxes(
        tickfont=dict(family=FONT_MONO, size=11, color=c["text_muted"]),
        gridcolor=c["border"],
        zerolinecolor=c["border"],
    )
    if showlegend:
        fig.update_layout(
            legend=dict(orientation="h", y=1.08,
                        font=dict(size=12, color=c["text"])),
        )
    return fig
