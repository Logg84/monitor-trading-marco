"""
theme.py v3 — gestione tema chiaro/scuro ARGO.
Il toggle vive nella navbar (nav.py): scelta globale per tutte le pagine.
Uso nelle pagine:
    from theme import get_theme, theme_css
    st.markdown(theme_css(), unsafe_allow_html=True)   # già iniettato da render_navbar()
    th = get_theme()                                  # colori per inline/grafici
"""
import streamlit as st

THEMES = {
    "dark": {
        "name": "dark",
        "bg_base": "#0a0f1a", "bg_panel": "#0f172a", "bg_panel2": "#111827",
        "bg_hover": "rgba(56,189,248,0.08)",
        "border": "#1e293b", "border_strong": "#334155",
        "txt1": "#f8fafc", "txt2": "#cbd5e1", "txt3": "#94a3b8", "muted": "#64748b",
        "accent": "#38bdf8",
        "font_head": "'Space Grotesk', 'Inter', sans-serif",
        "warn": {"bg": "rgba(245,158,11,0.08)", "fg": "#fcd34d", "strong": "#fef3c7"},
        "pills": {
            "green":  ("rgba(34,197,94,.16)",  "#86efac"),
            "amber":  ("rgba(245,158,11,.16)", "#fcd34d"),
            "red":    ("rgba(239,68,68,.16)",  "#fca5a5"),
            "blue":   ("rgba(96,165,250,.16)", "#93c5fd"),
            "violet": ("rgba(167,139,250,.20)","#d8b4fe"),
            "cyan":   ("rgba(0,180,216,.20)",  "#67e8f9"),
            "gray":   ("rgba(148,163,184,.12)","#cbd5e1"),
        },
        "score": {
            "hi":  ("#065f46", "#a7f3d0"),
            "mid": ("#143524", "#86efac"),
            "warn":("#3a2408", "#fde68a"),
            "low": ("#3a1414", "#fca5a5"),
            "health_mid": ("#78350f", "#fde68a"),
            "health_low": ("#7f1d1d", "#fca5a5"),
        },
        "chart": {
            "template": "plotly_dark",
            "paper": "rgba(0,0,0,0)", "plot": "#0d1526",
            "grid": "#2a3650", "axis": "#8ea3c0", "text": "#e2e8f0",
            "price": "#f8fafc",
            "roc": "#e879f9", "roc_fill": "rgba(232,121,249,0.18)",
            "poc_strong": "#ff4d6d", "poc_mid": "#fbbf24", "poc_min": "#94a3b8",
            "zone": "#facc15", "zone_fill": "rgba(250,204,21,0.14)",
            "up": "#22c55e", "down": "#ef4444",
            "vrect_up": "rgba(34,197,94,0.22)", "vrect_down": "rgba(239,68,68,0.16)",
            "marker_roc": "#00e676",
        },
    },
    "light": {
        "name": "light",
        "bg_base": "#eef2f7", "bg_panel": "#ffffff", "bg_panel2": "#f8fafc",
        "bg_hover": "rgba(2,132,199,0.08)",
        "border": "#dbe3ec", "border_strong": "#b6c2d2",
        "txt1": "#0f172a", "txt2": "#334155", "txt3": "#475569", "muted": "#8194a8",
        "accent": "#0284c7",
        "font_head": "'Space Grotesk', 'Inter', sans-serif",
        "warn": {"bg": "rgba(217,119,6,.10)", "fg": "#92400e", "strong": "#78350f"},
        "pills": {
            "green":  ("rgba(22,163,74,.12)",  "#15803d"),
            "amber":  ("rgba(217,119,6,.12)",  "#b45309"),
            "red":    ("rgba(220,38,38,.12)",  "#b91c1c"),
            "blue":   ("rgba(37,99,235,.12)",  "#1d4ed8"),
            "violet": ("rgba(124,58,237,.14)", "#6d28d9"),
            "cyan":   ("rgba(8,145,178,.14)",  "#0e7490"),
            "gray":   ("rgba(100,116,139,.14)","#334155"),
        },
        "score": {
            "hi":  ("#dcfce7", "#14532d"),
            "mid": ("#ecfdf5", "#065f46"),
            "warn":("#fef3c7", "#92400e"),
            "low": ("#fee2e2", "#991b1b"),
            "health_mid": ("#fef3c7", "#92400e"),
            "health_low": ("#fee2e2", "#991b1b"),
        },
        "chart": {
            "template": "plotly_white",
            "paper": "rgba(0,0,0,0)", "plot": "#ffffff",
            "grid": "#e2e8f0", "axis": "#475569", "text": "#0f172a",
            "price": "#0f172a",
            "roc": "#c026d3", "roc_fill": "rgba(192,38,211,0.12)",
            "poc_strong": "#e11d48", "poc_mid": "#d97706", "poc_min": "#64748b",
            "zone": "#ca8a04", "zone_fill": "rgba(202,138,4,0.12)",
            "up": "#16a34a", "down": "#dc2626",
            "vrect_up": "rgba(22,163,74,0.14)", "vrect_down": "rgba(220,38,38,0.10)",
            "marker_roc": "#16a34a",
        },
    },
}


def get_theme() -> dict:
    return THEMES.get(st.session_state.get("argo_theme", "dark"), THEMES["dark"])


def render_theme_toggle():
    """DEPRECATO: il toggle ora vive nella navbar (nav.py). No-op di compatibilità."""
    return None


def theme_css() -> str:
    th = get_theme()
    w = th["warn"]
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600;700&display=swap');
:root {{
  /* naming esteso (nav / app / metric_guide) */
  --bg-base: {th['bg_base']}; --bg-panel: {th['bg_panel']}; --bg-panel-2: {th['bg_panel2']};
  --bg-hover: {th['bg_hover']}; --border: {th['border']}; --border-strong: {th['border_strong']};
  --txt-1: {th['txt1']}; --txt-2: {th['txt2']}; --txt-3: {th['txt3']}; --txt-muted: {th['muted']};
  --accent: {th['accent']};
  --green: #22c55e; --yellow: #f59e0b; --red: #ef4444; --violet: #a78bfa; --cyan: #06b6d4;
  --warn-bg: {w['bg']}; --warn-fg: {w['fg']}; --warn-strong: {w['strong']};
  /* naming corto (screening) */
  --bg-panel2: {th['bg_panel2']}; --txt1: {th['txt1']}; --txt2: {th['txt2']};
  --txt3: {th['txt3']}; --muted: {th['muted']}; --font-head: {th['font_head']};
}}

/* === Sfondo reale dell'app (Streamlit moderno) === */
html, body, .stApp, section.main, .main,
[data-testid="stAppViewContainer"], [data-testid="stMainFrame"],
[data-testid="stAppViewBlockContainer"], .block-container {{
  background: var(--bg-base) !important;
}}
section[data-testid="stSidebar"] {{
  background: var(--bg-panel) !important;
  border-right: 1px solid var(--border);
}}

/* === Testo default (gli inline style vincono comunque) === */
body, p, li, label, span[data-testid="stCaptionContainer"],
[data-testid="stMarkdownContainer"], [data-testid="stMarkdownContainer"] p,
.stMarkdown, .stRadio label, .stSelectbox label, .stTextInput label,
.stNumberInput label, .stCheckbox label {{
  color: var(--txt-2);
}}
h1, h2, h3, h4, h5, h6 {{
  color: var(--txt-1) !important;
  font-family: var(--font-head);
}}
hr {{ border-color: var(--border) !important; }}

/* === Input / select / textarea === */
div[data-testid="stTextInput"] input, div[data-testid="stNumberInput"] input,
div[data-testid="stSelectbox"] [data-baseweb="select"] > div,
div[data-testid="stTextArea"] textarea {{
  background: var(--bg-panel) !important;
  color: var(--txt-1) !important;
  border: 1px solid var(--border) !important;
}}

/* === Bottoni === */
div[data-testid="stButton"] button {{
  background: var(--bg-panel); color: var(--txt-2);
  border: 1px solid var(--border-strong); border-radius: 8px;
  transition: all .15s ease;
}}
div[data-testid="stButton"] button:hover {{
  border-color: var(--accent); color: var(--accent); background: var(--bg-hover);
}}
div[data-testid="stButton"] button[type="primary"], div[data-testid="stButton"] button[kind="primary"] {{
  background: var(--accent) !important; color: #ffffff !important; border-color: var(--accent) !important;
}}

/* === Tabs === */
button[data-testid="stTabButton"] {{ color: var(--txt-3); }}
button[data-testid="stTabButton"][aria-selected="true"] {{
  color: var(--accent); border-color: var(--accent);
}}

/* === Expander === */
details[data-testid="stExpander"] {{
  background: var(--bg-panel); border: 1px solid var(--border); border-radius: 10px;
}}
details[data-testid="stExpander"] summary {{ color: var(--txt-2); }}
details[data-testid="stExpander"] summary p {{ color: var(--txt-2); }}

/* === Alert box (info/warning/error/success) === */
div[data-testid="stAlert"] {{ background: var(--bg-panel) !important; }}

/* === Dataframe === */
div[data-testid="stDataFrame"] {{ border: 1px solid var(--border); border-radius: 10px; }}
[data-testid="stDataFrame"] [role="columnheader"] {{
  background: var(--bg-panel) !important; color: var(--txt-3) !important;
}}
[data-testid="stDataFrame"] [role="gridcell"] {{ color: var(--txt-2); }}

/* === Metric === */
div[data-testid="stMetric"] label {{ color: var(--txt-3); }}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {{ color: var(--txt-1); }}

/* === File uploader === */
div[data-testid="stFileUploaderDropzone"] {{
  background: var(--bg-panel); border: 1px dashed var(--border-strong);
}}
</style>
"""
