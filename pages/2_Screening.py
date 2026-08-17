import streamlit as st
import pandas as pd
import yfinance as yf
import json
import os
import html
import requests
import io
import base64
import datetime
import numpy as np
import time
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import traceback
from data_engine import DataEngine, MAX_POC_DIST_PCT
from nav import render_navbar, section_header
from metric_guide import render_metric_guide
from theme import render_theme_toggle, get_theme, theme_css

st.set_page_config(page_title="ARGO Screening", layout="wide", page_icon="🎛️")

from watchlist_io import (
    carica_watchlist_da_github,
    commit_csv_su_github,
    promuovi_auto_da_screener,
    GITHUB_TOKEN,
    GITHUB_REPO,
)

try:
    from streamlit_autorefresh import st_autorefresh
    _HAS_AUTOREFRESH = True
except ImportError:
    _HAS_AUTOREFRESH = False

if _HAS_AUTOREFRESH:
    st_autorefresh(interval=600000, key="argo_screening_refresh")

render_theme_toggle()
st.markdown(theme_css(), unsafe_allow_html=True)
TH = get_theme()

st.markdown("""
<style>
.block-container { padding-top: 1.5rem; padding-bottom: 1rem; padding-left: 1.25rem; padding-right: 1.25rem; max-width: 100%; }
h1 { font-size: 1.7rem !important; margin-bottom: 0.2rem !important; }
section[data-testid="stSidebar"] { width: 260px !important; min-width: 260px !important; }
section[data-testid="stSidebar"] > div { width: 260px !important; }

.argo-report {
    position: relative; overflow: hidden;
    background: linear-gradient(135deg, var(--bg-panel) 0%, var(--bg-panel2) 100%);
    border: 1px solid var(--border); border-left: 5px solid var(--accent);
    border-radius: 12px; padding: 16px 18px; margin: 4px 0 18px 0;
}
.argo-report .ar-head { position: relative; font-family: 'IBM Plex Mono', monospace; font-size: 11px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: var(--accent); margin-bottom: 12px; }
.argo-report .ar-chips { position: relative; display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.argo-report .ar-chip { background: var(--bg-base); border: 1px solid var(--border-strong); border-radius: 8px; padding: 7px 12px; min-width: 92px; text-align: left; }
.argo-report .ar-num { font-family: 'IBM Plex Mono', monospace; font-size: 22px; font-weight: 700; line-height: 1; }
.argo-report .ar-lab { font-size: 10px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--txt3); margin-top: 4px; }
.argo-report .ar-note { position: relative; font-size: 13px; color: var(--txt2); line-height: 1.55; }
.argo-report .ar-note b { color: var(--txt1); }
.argo-report .ar-add { color: #22c55e; }
.argo-report .ar-upd { color: #60a5fa; }
.argo-report .ar-vw { color: #38bdf8; }
.argo-report .ar-rm { color: #f59e0b; }
.argo-report .ar-tags { position: relative; margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--border); display: flex; flex-direction: column; gap: 9px; }
.argo-report .ar-group { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.argo-report .ar-glabel { font-family: 'IBM Plex Mono', monospace; font-size: 10px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; margin-right: 2px; }
.argo-report .ar-tag { font-family: 'IBM Plex Mono', monospace; font-size: 11.5px; font-weight: 600; padding: 3px 10px; border-radius: 999px; border: 1px solid transparent; background: var(--bg-base); }
.argo-report .ar-tag.ar-add { color: #86efac; border-color: rgba(34,197,94,.45); background: rgba(34,197,94,.10); }
.argo-report .ar-tag.ar-upd { color: #93c5fd; border-color: rgba(96,165,250,.45); background: rgba(96,165,250,.10); }
.argo-report .ar-tag.ar-vw { color: #67e8f9; border-color: rgba(56,189,248,.45); background: rgba(56,189,248,.10); }
.argo-report .ar-tag.ar-rm { color: #fca5a5; border-color: rgba(239,68,68,.45); background: rgba(239,68,68,.10); }
.argo-report .ar-tag.ar-tag-more { color: var(--txt3); border-color: var(--border-strong); }

.sk-cap { font-family: 'IBM Plex Mono', monospace; font-size: 10px; letter-spacing: .12em; text-transform: uppercase; color: var(--txt3); margin: 2px 0 6px 0; }

/* RIGHE NATIVE: niente tagli, testo completo e leggibile */
.screening-row { border-bottom: 1px solid var(--border); padding: 6px 0; }
.screening-row > div { white-space: normal !important; overflow: visible !important; }
.screening-row .cell-txt { font-size: 12.5px; color: var(--txt2); line-height: 1.45; }
.screening-row .cell-num { font-family: 'IBM Plex Mono', monospace; font-size: 12.5px; color: var(--txt1); }
.screening-row .cell-muted { color: var(--muted); }
.screening-row .hdr { font-family: 'IBM Plex Mono', monospace; font-size: 10.5px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--txt3); }
.screening-row .det-full { font-size: 12px; color: var(--txt3); line-height: 1.5; white-space: normal !important; }

.decel-inline {
    border: 1px solid var(--border); border-left: 4px solid var(--accent);
    background: var(--bg-panel);
    border-radius: 12px; padding: 14px 16px; margin: 8px 0 12px 0;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------
# MOTORE
# ---------------------------------------------------------------
if "engine" not in st.session_state:
    st.session_state["engine"] = DataEngine()
engine = st.session_state["engine"]

macro_info = engine.ottieni_bussola_argo()
argo_bussola = macro_info["bussola"]

render_navbar("screening", hide_sidebar=False, bussola=argo_bussola)
section_header("Terminale operativo", "Screening & Titoli in Sconto")

with st.expander("ℹ️ Legenda Health Check", expanded=False):
    st.markdown("""
    **Health Check** – Valutazione assoluta della salute finanziaria (0-4):
    - 🔹 **Free Cash Flow** TTM > 0 → l'azienda genera cassa operativa
    - 🔹 **Crescita Ricavi** YoY > 0 → fatturato in espansione
    - 🔹 **Utile Netto** > 0 → redditività positiva
    - 🔹 **Debito / Patrimonio Netto** < 1.5 → indebitamento contenuto
    """)

if "screener_database" not in st.session_state:
    st.session_state["screener_database"] = engine.screener_database
if "ultimi_spostamenti" not in st.session_state:
    st.session_state["ultimi_spostamenti"] = []
if "argo_prev_stato" not in st.session_state:
    st.session_state["argo_prev_stato"] = None
if "argo_prev_color" not in st.session_state:
    st.session_state["argo_prev_color"] = None
if "argo_state_changed" not in st.session_state:
    st.session_state["argo_state_changed"] = False
if "scan_timestamps" not in st.session_state:
    st.session_state["scan_timestamps"] = {
        "S&P 500": None, "NASDAQ 100": None, "DAX (Germania)": None,
        "CAC 40 (Francia)": None, "FTSE MIB (Italia)": None
    }
if "debug_log" not in st.session_state:
    st.session_state["debug_log"] = engine.debug_log
if "ultimo_report_auto" not in st.session_state:
    st.session_state["ultimo_report_auto"] = None
if "screening_fatto_in_sessione" not in st.session_state:
    st.session_state["screening_fatto_in_sessione"] = False


def carica_database_da_github() -> dict | None:
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return None
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/argo_database.json"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code != 200:
            return None
        contenuto = base64.b64decode(r.json()["content"]).decode()
        return json.loads(contenuto)
    except Exception as e:
        print(f"Errore lettura argo_database.json da GitHub: {e}")
        return None


if not st.session_state["screening_fatto_in_sessione"]:
    _db_gh = carica_database_da_github()
    if _db_gh:
        engine.screener_database.clear()
        engine.screener_database.update(_db_gh)
        st.session_state["screener_database"] = engine.screener_database
        _ls = _db_gh.get("_last_scans", {}) or {}
        for _idx in st.session_state["scan_timestamps"]:
            if st.session_state["scan_timestamps"][_idx] is None and _idx in _ls:
                try:
                    st.session_state["scan_timestamps"][_idx] = datetime.datetime.fromisoformat(_ls[_idx])
                except Exception:
                    pass


def genera_url_tradingview(ticker):
    t = str(ticker).upper().strip()
    if t.endswith('.DE'):
        return f"https://www.tradingview.com/symbols/XETR-{t.replace('.DE', '')}/"
    elif t.endswith('.MI'):
        return f"https://www.tradingview.com/symbols/MIL-{t.replace('.MI', '')}/"
    elif t.endswith('.PA'):
        return f"https://www.tradingview.com/symbols/EPA-{t.replace('.PA', '')}/"
    else:
        return f"https://www.tradingview.com/symbols/{t}/"


def pulisci_auto_zombie(indice: str, ticker_correnti_set: set):
    df_wl = carica_watchlist_da_github()
    if df_wl.empty:
        return 0, []
    tag = f"({indice})"
    idx_da_togliere, rimossi_t = [], []
    for idx, row in df_wl.iterrows():
        origine = str(row.get("Origine", "")).strip().lower()
        auto_idx = str(row.get("Auto_Indice", "")).strip()
        nota_poc = str(row.get("Nota POC 1", "")) + str(row.get("Nota POC", ""))
        is_mine = (auto_idx == indice) or (origine == "auto" and tag in nota_poc)
        if origine == "auto" and is_mine:
            tk = str(row["Ticker"]).strip().upper()
            if tk not in ticker_correnti_set:
                idx_da_togliere.append(idx); rimossi_t.append(tk)
    if idx_da_togliere:
        df_wl = df_wl.drop(idx_da_togliere)
        commit_csv_su_github(df_wl)
    return len(idx_da_togliere), rimossi_t


def check_state_change():
    prev_stato = st.session_state.get("argo_prev_stato")
    prev_color = st.session_state.get("argo_prev_color")
    current_stato = argo_bussola["stato"]
    current_color = argo_bussola["color"]
    if prev_stato is not None and prev_stato != current_stato:
        st.session_state["argo_state_changed"] = True
        st.session_state["argo_old_stato"] = prev_stato
        st.session_state["argo_old_color"] = prev_color
        st.session_state["argo_new_stato"] = current_stato
        st.session_state["argo_new_color"] = current_color
    else:
        st.session_state["argo_state_changed"] = False
    st.session_state["argo_prev_stato"] = current_stato
    st.session_state["argo_prev_color"] = current_color


check_state_change()

color_map = {"emerald": "#10b981", "rose": "#f43f5e", "amber": "#f59e0b", "indigo": "#6366f1", "orange": "#f97316", "slate": "#64748b"}
st.markdown(f"""
<div style="background: var(--bg-panel); border: 1px solid var(--border); border-left: 5px solid {color_map[argo_bussola['color']]}; padding: 8px 14px; border-radius: 8px; margin-bottom: 15px; margin-top: 5px;">
    <div style="display: flex; justify-content: space-between; align-items: center; gap: 12px;">
        <div>
            <span style="font-size: 9px; font-weight: bold; text-transform: uppercase; color: var(--txt3);">Direttiva Tattica</span>
            <h5 style="margin: 0; color: var(--txt1); font-weight: 800; font-size: 1.15rem;">{argo_bussola['stato']}</h5>
            <p style="margin: 0; font-size: 12px; color: var(--txt2); font-weight: 500;">{argo_bussola['desc']}</p>
        </div>
        <div style="background: var(--bg-base); border: 1px solid var(--border-strong); padding: 6px 12px; border-radius: 6px; text-align: center;">
            <span style="font-size: 8px; font-weight: bold; color: var(--txt3); text-transform: uppercase;">BIAS</span>
            <h4 style="margin: 0; color: {color_map[argo_bussola['color']]}; font-weight: 900; font-size: 1.1rem;">{argo_bussola['bias']}</h4>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------
listino_opzioni = ["🌍 TUTTI GLI INDICI INSIEME", "S&P 500", "NASDAQ 100", "DAX (Germania)", "CAC 40 (Francia)", "FTSE MIB (Italia)"]

with st.sidebar:
    st.header("⚙️ Configurazione Metodo REA")
    indice_scelto = st.selectbox("Seleziona l'Indice da Scansionare:", listino_opzioni)
    st.markdown("---")
    default_cap = 10.0 if indice_scelto in ["S&P 500", "NASDAQ 100", "🌍 TUTTI GLI INDICI INSIEME"] else 2.5
    min_market_cap = st.number_input("Market Cap Minima (Miliardi): ", value=default_cap, step=0.5) * 1e9
    soglia_drawdown = st.number_input("Soglia Minima di Drawdown dall'ATH (%) ", value=25.0, step=5.0)
    st.markdown("---")
    soglia_poc_pct = st.number_input("Soglia Vicinanza POC / VWAP (%) ", value=2.0, step=0.5)
    st.markdown("---")
    soglia_promo_pct = st.number_input("Soglia promozione auto in watchlist (%) ", value=2.5, step=0.5)
    st.markdown("---")
    st.caption("💡  Health Check (0-4):  salute finanziaria assoluta.")
    st.caption("📉  Bottom Score (0-4):  segnali di inversione.")
    st.caption("⚖️  Operazione Potenziale:  lettura non vincolante.")
    st.caption("⏰  Screening automatico:  21:30 UTC.")

    st.markdown("---")
    st.subheader("🕒 Stato Scansioni")
    for idx_name, ts in st.session_state["scan_timestamps"].items():
        if ts is None:
            st.caption(f"❌ {idx_name}: Mai scansionato")
        else:
            delta = (datetime.datetime.now() - ts).total_seconds() / 60
            if delta < 60:
                st.caption(f"✅ {idx_name}: {int(delta)} minuti fa")
            else:
                st.caption(f"✅ {idx_name}: {ts.strftime('%H:%M %d/%m')}")

    st.markdown("---")
    if st.button("🚀 AVVIA SCREENING QUALITY (v2)", type="primary", use_container_width=True):
        engine.debug_log = []
        st.session_state["debug_log"] = []
        st.session_state["ultimi_spostamenti"] = []
        st.session_state["ultimo_report_auto"] = None
        total_spostamenti, total_count = [], 0
        tot_agg, tot_upd, tot_vw, tot_zomb, tot_in_zona = 0, 0, 0, 0, 0
        tot_agg_t, tot_upd_t, tot_vw_t, tot_zomb_t = [], [], [], []

        if indice_scelto == "🌍 TUTTI GLI INDICI INSIEME":
            indices_to_scan = ["S&P 500", "NASDAQ 100", "DAX (Germania)", "CAC 40 (Francia)", "FTSE MIB (Italia)"]
        else:
            indices_to_scan = [indice_scelto]

        for idx_name in indices_to_scan:
            with st.spinner(f"Scansione in corso per {idx_name}..."):
                result_list, spost = engine.perform_screening(idx_name, min_market_cap, soglia_drawdown, soglia_poc_pct)
                if result_list:
                    total_spostamenti.extend(spost); total_count += len(result_list)
                    st.session_state[f"scan_count_{idx_name}"] = len(result_list)
                else:
                    st.session_state[f"scan_count_{idx_name}"] = 0
                st.session_state["scan_timestamps"][idx_name] = datetime.datetime.now()
                st.session_state[f"has_scanned_{idx_name}"] = True

                df_scr = pd.DataFrame(result_list) if result_list else pd.DataFrame()
                stats = promuovi_auto_da_screener(df_scr, idx_name, soglia_trigger_pct=soglia_promo_pct)
                tot_agg += stats.get("aggiunti", 0); tot_upd += stats.get("aggiornati", 0)
                tot_vw += stats.get("vwappati", 0); tot_in_zona += stats.get("in_zona", 0)
                tot_agg_t += stats.get("aggiunti_tickers", []); tot_upd_t += stats.get("aggiornati_tickers", [])
                tot_vw_t += stats.get("vwappati_tickers", [])
                ticker_correnti = set(str(t).strip().upper() for t in df_scr["Ticker"]) if (not df_scr.empty and "Ticker" in df_scr.columns) else set()
                zcount, zlist = pulisci_auto_zombie(idx_name, ticker_correnti)
                tot_zomb += zcount; tot_zomb_t += zlist

        st.session_state["ultimi_spostamenti"] = total_spostamenti
        st.session_state["scan_count_all"] = total_count
        st.session_state["ultimo_report_auto"] = {
            "aggiunti": tot_agg, "aggiornati": tot_upd, "vwappati": tot_vw,
            "rimossi": tot_zomb, "in_zona": tot_in_zona, "soglia": soglia_promo_pct,
            "aggiunti_tickers": tot_agg_t, "aggiornati_tickers": tot_upd_t,
            "vwappati_tickers": tot_vw_t, "rimossi_tickers": tot_zomb_t,
        }
        st.session_state["screening_fatto_in_sessione"] = True
        st.success(f"✅ Scansione completata! Trovati {total_count} titoli in totale su {len(indices_to_scan)} indici.")
        st.rerun()

    st.markdown("---")
    st.subheader("🔍 Debug Log (ultimi 50 eventi)")
    _live_log = engine.debug_log
    if _live_log:
        for entry in _live_log[-50:]:
            level = entry["level"]
            color = {"info": "#60a5fa", "success": "#22c55e", "error": "#ef4444", "warning": "#eab308"}.get(level, "#94a3b8")
            st.markdown(f"<div style='font-size:11.5px; color:{color};'>[{entry['time']}] {entry['msg']}</div>", unsafe_allow_html=True)
    else:
        st.caption("Nessun evento di debug registrato.")

# ---------------------------------------------------------------
# PANNELLO AUTOMAZIONE
# ---------------------------------------------------------------
rep = st.session_state.get("ultimo_report_auto")
if rep is not None:
    soglia_rep = rep.get("soglia", 2.5)
    chips = (
        f'<div class="ar-chip"><div class="ar-num ar-add">{rep["aggiunti"]}</div><div class="ar-lab">➕ Aggiunti </div></div>'
        f'<div class="ar-chip"><div class="ar-num ar-upd">{rep["aggiornati"]}</div><div class="ar-lab">🔄 Auto aggiornati</div></div>'
        f'<div class="ar-chip"><div class="ar-num ar-vw">{rep["vwappati"]}</div><div class="ar-lab">🔃 VWAP rinfrescati</div></div>'
        f'<div class="ar-chip"><div class="ar-num ar-rm">{rep["rimossi"]}</div><div class="ar-lab">🗑️ Usciti (no sconto)</div></div>'
        f'<div class="ar-chip"><div class="ar-num" style="color:var(--txt1)">{rep["in_zona"]}</div><div class="ar-lab">🎯 In zona (≤{soglia_rep:g}%)</div></div>'
    )

    def _pills(names, cls, maxn=8):
        if not names:
            return ""
        names = list(dict.fromkeys(str(n) for n in names))
        shown = names[:maxn]; extra = len(names) - len(shown)
        inner = "".join(f'<span class="ar-tag {cls}">{html.escape(n)}</span>' for n in shown)
        if extra > 0:
            inner += f'<span class="ar-tag ar-tag-more">+{extra}</span>'
        return inner

    groups = [
        (rep.get("aggiunti_tickers"), "ar-add", "➕ Entrati"),
        (rep.get("aggiornati_tickers"), "ar-upd", "🔄 Aggiornati"),
        (rep.get("vwappati_tickers"), "ar-vw", "🔃 VWAP rinfrescati"),
        (rep.get("rimossi_tickers"), "ar-rm", "🗑️ Usciti"),
    ]
    group_html = []
    for names, cls, label in groups:
        pills = _pills(names, cls)
        if pills:
            group_html.append(f'<div class="ar-group"><span class="ar-glabel {cls}">{label}</span>{pills}</div>')
    detail_html = '<div class="ar-tags">' + "".join(group_html) + '</div>' if group_html else ''

    if rep["in_zona"] == 0 and not group_html:
        nota = (f"Nessun titolo dello screening era dentro una zona POC o vicino a un VWAP (±{soglia_rep:g}%): "
                f"<b>niente nuovi ingressi</b> e nessun VWAP da rinfrescare in questo giro.")
    elif not group_html:
        nota = f"<b>{rep['in_zona']}</b> titoli in zona, ma nessuno ha cambiato stato né VWAP rispetto a prima."
    else:
        parti = []
        if rep["aggiunti"]:
            parti.append(f"<span class='ar-add'><b>{rep['aggiunti']}</b> nuovi 🤖</span>")
        if rep["aggiornati"]:
            parti.append(f"<span class='ar-upd'><b>{rep['aggiornati']}</b> auto aggiornati</span>")
        if rep["vwappati"]:
            parti.append(f"<span class='ar-vw'><b>{rep['vwappati']}</b> manuali con VWAP rinfrescati</span>")
        nota = f"Esito: {' · '.join(parti)}." if parti else "Nessun cambiamento di stato in questo giro."
    extra = f" <span class='ar-rm'>🗑️ {rep['rimossi']}</span> auto rimossi perché non più in sconto." if rep["rimossi"] else ""

    st.markdown(
        '<div class="argo-report"><div class="ar-head">🤖 Automazione watchlist — esito dell\'ultimo screening</div>'
        '<div class="ar-chips">' + chips + '</div><div class="ar-note">' + nota + extra + '</div>'
        + detail_html + '</div>',
        unsafe_allow_html=True,
    )

render_metric_guide()

# ---------------------------------------------------------------
# HELPER CELLE (tema-aware, alto contrasto)
# ---------------------------------------------------------------
_CHIPS = ["Ticker", "Prezzo", "DD%", "Health", "Bottom", "MCap", "dPOC%", "dVWAP%"]
_CHIP2COL = {
    "Ticker": "Ticker", "Prezzo": "Prezzo", "DD%": "Drawdown (%)",
    "Health": "Health_Score", "Bottom": "Bottom Score (0-4)",
    "MCap": "Market Cap (B)", "dPOC%": "_dist_poc_num", "dVWAP%": "Distanza VWAP (%)",
}
_CHIP_DIR = {
    "Ticker": "asc", "Prezzo": "desc", "DD%": "asc", "Health": "desc",
    "Bottom": "desc", "MCap": "desc", "dPOC%": "asc", "dVWAP%": "asc",
}


def _sf(v):
    try:
        f = float(v)
        return np.nan if pd.isna(f) else f
    except (TypeError, ValueError):
        return np.nan


def _isna(v):
    if v is None:
        return True
    try:
        if isinstance(v, float) and pd.isna(v):
            return True
    except Exception:
        pass
    return str(v).strip().lower() in ("", "nan", "none")


def _parse_pct(s):
    s = str(s).strip()
    if s in ("", "nan", "None", "N/D"):
        return np.nan
    try:
        return float(s.replace("%", "").replace("+", ""))
    except Exception:
        return np.nan


def arricchisci(df, soglia):
    if df.empty:
        for c in ["VWAP vicino", "_vwap_tf", "Distanza VWAP (%)", "_dist_poc_num", "🎯 Alert", "_alert_detail"]:
            df[c] = np.nan if c in ("VWAP vicino", "Distanza VWAP (%)", "_dist_poc_num") else ""
        return df

    def _vwap_nearest(row):
        P = _sf(row.get("Prezzo"))
        cands = []
        for tf, key in (("3M", "VWAP 3M"), ("1Y", "VWAP 1Y"), ("4Y", "VWAP 4Y")):
            v = _sf(row.get(key))
            if v > 0 and P > 0:
                d = (P - v) / v * 100
                cands.append((abs(d), d, v, tf))
        if not cands:
            return pd.Series({"VWAP vicino": 0.0, "_vwap_tf": "", "Distanza VWAP (%)": np.nan})
        cands.sort(key=lambda x: x[0])
        _, d, v, tf = cands[0]
        return pd.Series({"VWAP vicino": round(v, 2), "_vwap_tf": tf, "Distanza VWAP (%)": round(d, 1)})

    df = df.copy()
    df[["VWAP vicino", "_vwap_tf", "Distanza VWAP (%)"]] = df.apply(_vwap_nearest, axis=1)
    df["_dist_poc_num"] = df["Distanza POC (%)"].apply(_parse_pct)

    def _alert(row):
        P = _sf(row.get("Prezzo"))
        in_zona = False
        for k in (1, 2, 3):
            poc_low = _sf(row.get(f"POC {k} Low"))
            poc_high = _sf(row.get(f"POC {k} High"))
            if poc_low > 0 and poc_high > 0 and P > 0:
                if poc_low <= P <= poc_high:
                    in_zona = True
                    break
        poc_hit = in_zona or (str(row.get("🎯 ALERT POC", "")).strip() == "🎯 SU POC")
        dv = row["Distanza VWAP (%)"]
        vwap_hit = pd.notna(dv) and abs(dv) <= soglia
        dp = row["_dist_poc_num"]
        if not poc_hit and not vwap_hit:
            return pd.Series({"🎯 Alert": "", "_alert_detail": ""})
        parts = []
        if poc_hit:
            parts.append("POC 📍 in zona" if in_zona else (f"POC {dp:+.1f}%" if pd.notna(dp) else "POC"))
        if vwap_hit:
            parts.append(f"VWAP {dv:+.1f}%")
        label = "🎯 POC+VWAP" if (poc_hit and vwap_hit) else ("🎯 IN ZONA POC" if in_zona else ("🎯 SU POC" if poc_hit else "🎯 SU VWAP"))
        return pd.Series({"🎯 Alert": label, "_alert_detail": " · ".join(parts)})

    df[["🎯 Alert", "_alert_detail"]] = df.apply(_alert, axis=1)

    def _format_dist_poc(row):
        P = _sf(row.get("Prezzo"))
        for k in (1, 2, 3):
            poc_low = _sf(row.get(f"POC {k} Low"))
            poc_high = _sf(row.get(f"POC {k} High"))
            if poc_low > 0 and poc_high > 0 and P > 0:
                if poc_low <= P <= poc_high:
                    return "📍 in zona"
        return row.get("Distanza POC (%)", "N/D")

    df["Distanza POC (%)"] = df.apply(_format_dist_poc, axis=1)
    return df


def _fmt2(v):
    if _isna(v):
        return "—"
    try:
        return f"{float(v):.2f}"
    except Exception:
        return html.escape(str(v))


def _pill(text, key):
    bg, fg = TH["pills"][key]
    return f'<span style="background:{bg};color:{fg};padding:2px 9px;border-radius:999px;font-size:11px;font-weight:700;white-space:nowrap;">{html.escape(str(text))}</span>'


def _entry_cell(v):
    s = str(v)
    if s.startswith("🚀"): return _pill(s, "green")
    if s.startswith("⏳"): return _pill(s, "amber")
    if s.startswith("⛔"): return _pill(s, "red")
    if s.startswith("📈"): return _pill(s, "blue")
    return _pill(s, "gray")


def _stato_cell(v):
    s = str(v).strip()
    if s == "Active": return _pill(s, "green")
    if s == "Ripartito": return _pill(s, "amber")
    if s == "Nuovo": return _pill(s, "blue")
    return _pill(s or "—", "gray")


def _alert_cell(val, row):
    label = str(val).strip()
    if not label:
        return '<span class="cell-muted">—</span>'
    detail = str(row.get("_alert_detail", "")).strip() if row is not None else ""
    if "POC+VWAP" in label:
        key = "violet"
    elif "IN ZONA" in label:
        key = "green"
    elif "SU POC" in label:
        key = "red"
    else:
        key = "cyan"
    inner = _pill(label, key)
    if detail:
        inner += f'<div class="det-full" style="margin-top:3px;">{html.escape(detail)}</div>'
    return inner


def _health_div(score, label):
    sc = TH["score"]
    if score == 4:
        bg, fg = sc["hi"]
    elif score >= 2:
        bg, fg = sc["health_mid"]
    else:
        bg, fg = sc["health_low"]
    return f'<span style="background:{bg};color:{fg};padding:2px 8px;border-radius:6px;font-weight:800;font-family:\'IBM Plex Mono\',monospace;">{html.escape(str(label))}</span>'


def _bottom_div(v):
    sc = TH["score"]
    if v >= 4: bg, fg = sc["hi"]
    elif v >= 3: bg, fg = sc["mid"]
    elif v >= 2: bg, fg = sc["warn"]
    else: bg, fg = sc["low"]
    disp = str(int(v)) if float(v).is_integer() else f"{float(v):.1f}"
    return f'<span style="background:{bg};color:{fg};padding:2px 8px;border-radius:6px;font-weight:800;font-family:\'IBM Plex Mono\',monospace;">{disp}</span>'


def render_sort_bar(key, default_chip):
    cur_chip = st.session_state.get(f"{key}_chip", default_chip)
    cur_dir = st.session_state.get(f"{key}_dir", _CHIP_DIR[default_chip])
    st.markdown('<div class="sk-cap">↕️ Ordina per</div>', unsafe_allow_html=True)
    cols = st.columns(len(_CHIPS))
    for c, chip in zip(cols, _CHIPS):
        active = (chip == cur_chip)
        arrow = "▲ " if (active and cur_dir == "asc") else ("▼ " if (active and cur_dir == "desc") else "")
        if c.button(arrow + chip, key=f"{key}_s_{chip}", type="primary" if active else "secondary", use_container_width=True):
            nd = _CHIP_DIR[chip] if not active else ("asc" if cur_dir == "desc" else "desc")
            st.session_state[f"{key}_chip"] = chip
            st.session_state[f"{key}_dir"] = nd
            st.rerun()
    return _CHIP2COL[cur_chip], (cur_dir == "asc")


def _apply_sort(df, col, asc):
    if df.empty or col not in df.columns:
        return df
    return df.sort_values(by=col, ascending=asc, na_position="last", kind="mergesort")


# ---------------------------------------------------------------
# GRAFICO DECELERAZIONE (alto contrasto, tema-aware)
# ---------------------------------------------------------------
@st.cache_data(ttl=600)
def get_hist_for_ticker(ticker):
    try:
        hist = yf.download(ticker, period="10y", interval="1d", progress=False)
        if hist.empty:
            return None
        if isinstance(hist.columns, pd.MultiIndex):
            hist.columns = hist.columns.droplevel(-1)
        return hist
    except Exception:
        return None


def grafico_decelerazione(hist, ticker):
    if hist is None or len(hist) < 30:
        return None
    ch = TH["chart"]
    hist_full = hist.copy()
    df = hist.tail(250).copy()
    roc = df['Close'].pct_change(periods=20) * 100
    roc_smoothed = roc.rolling(5, min_periods=1).mean()
    roc_rising = roc_smoothed.diff() > 0
    pocs = engine.get_pocs_from_hist(hist_full)
    price_now = float(df['Close'].dropna().values[-1])
    for p in pocs:
        p["poc_price"] = float(p["poc_price"]); p["weight_norm"] = float(p.get("weight_norm", 5.0))
        p["dist_pct"] = round((price_now - p["poc_price"]) / p["poc_price"] * 100, 2)

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.65, 0.35], vertical_spacing=0.07)
    fig.add_trace(go.Scatter(
        x=df.index, y=df['Close'], mode='lines', name='Prezzo',
        line=dict(color=ch["price"], width=2.6),
        hovertemplate='<b>%{x|%d %b %Y}</b><br>Prezzo: <b>%{y:.2f}</b><extra></extra>'), row=1, col=1)

    for i in range(1, len(df)):
        color = ch["vrect_up"] if roc_rising.iloc[i] else ch["vrect_down"]
        fig.add_vrect(x0=df.index[i-1], x1=df.index[i], fillcolor=color, opacity=1, layer="below", line_width=0, row=1, col=1)

    for p in pocs:
        if abs(p["dist_pct"]) > MAX_POC_DIST_PCT:
            continue
        wn = float(p.get("weight_norm", 5.0)); poc_price = float(p["poc_price"])
        if wn >= 8:
            lcolor, lwidth, dash = ch["poc_strong"], 3.0, 'solid'
            importance_label = "🔴 STRUTTURALE"
        elif wn >= 5:
            lcolor, lwidth, dash = ch["poc_mid"], 2.2, 'dash'
            importance_label = "🟠 MEDIO"
        else:
            lcolor, lwidth, dash = ch["poc_min"], 1.4, 'dot'
            importance_label = "⚫ MINORE"
        fig.add_hline(y=poc_price, line=dict(color=lcolor, width=lwidth, dash=dash), opacity=0.95,
            annotation_text=f"POC {p['anchor_year']} · {poc_price:.2f} · {importance_label} (peso {wn:.0f}/10)",
            annotation_position="top right",
            annotation_font=dict(size=10, color=lcolor, family="IBM Plex Mono"),
            row=1, col=1)

    for i in range(1, len(roc_smoothed)):
        if (not pd.isna(roc_smoothed.iloc[i]) and not pd.isna(roc_smoothed.iloc[i-1]) and roc_smoothed.iloc[i-1] < 0 and roc_smoothed.iloc[i] >= 0):
            fig.add_trace(go.Scatter(
                x=[df.index[i]], y=[df['Close'].iloc[i]], mode='markers+text',
                marker=dict(symbol='triangle-up', size=15, color=ch["marker_roc"], line=dict(color=ch["price"], width=1.5)),
                text=["ROC+"], textposition="top center",
                textfont=dict(size=10, color=ch["marker_roc"], family="IBM Plex Mono"),
                name='Segnale ROC+', showlegend=False,
                hovertemplate=f'<b>Crossover ROC positivo</b><br>{df.index[i].strftime("%d %b %Y")}<br>Prezzo: %{{y:.2f}}<extra></extra>'), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=roc_smoothed.index, y=roc_smoothed, mode='lines', name='Velocità discesa',
        line=dict(color=ch["roc"], width=2.4), fill='tozeroy', fillcolor=ch["roc_fill"],
        hovertemplate='<b>%{x|%d %b %Y}</b><br>Velocità: <b>%{y:.1f}%</b><extra></extra>'), row=2, col=1)
    fig.add_hline(y=0, line_dash="solid", line_color=ch["axis"], opacity=0.9, row=2, col=1)
    fig.add_hrect(y0=-5, y1=5, fillcolor=ch["zone_fill"], line=dict(color=ch["zone"], width=1.5, dash="dot"),
        annotation_text="⚡ ZONA INVERSIONE (±5%)", annotation_position="top right",
        annotation_font=dict(size=10, color=ch["zone"], family="IBM Plex Mono"), row=2, col=1)

    fig.update_layout(
        template=ch["template"], height=660, margin=dict(l=10, r=10, t=50, b=10),
        hovermode='x unified', showlegend=False,
        paper_bgcolor=ch["paper"], plot_bgcolor=ch["plot"],
        font=dict(family="IBM Plex Mono, monospace", size=11.5, color=ch["text"]),
    )
    fig.update_yaxes(title_text="PREZZO", row=1, col=1, color=ch["axis"], gridcolor=ch["grid"], title_font=dict(size=10, family="IBM Plex Mono"))
    fig.update_yaxes(title_text="VELOCITÀ (%)", row=2, col=1, color=ch["axis"], gridcolor=ch["grid"], zeroline=False, title_font=dict(size=10, family="IBM Plex Mono"))
    fig.update_xaxes(gridcolor=ch["grid"], row=1, col=1)
    fig.update_xaxes(title_text="DATA", gridcolor=ch["grid"], row=2, col=1, title_font=dict(size=10, family="IBM Plex Mono"))
    return fig


def interpreta_bottom_score(score, dettagli):
    if score >= 4:
        return {"semaforo": "🟢", "titolo": "FORTE INVERSIONE", "colore": TH["chart"]["up"], "operazione": "✅ Pronto per l'ingresso. Il titolo è tecnicamente pronto a ripartire. Valutare l'acquisto con stop loss sotto il POC."}
    elif score == 3:
        return {"semaforo": "🟡", "titolo": "SEGNALI INIZIALI", "colore": TH["chart"]["zone"], "operazione": "🔍 Monitoraggio. La decelerazione è iniziata, ma manca ancora la conferma del volume o del POC."}
    elif score == 2:
        return {"semaforo": "🟡", "titolo": "ESAURIMENTO VENDITA", "colore": TH["chart"]["zone"], "operazione": "⏳ Pazienza. La discesa sta rallentando, ma non ci sono ancora segnali di acquisto attivi."}
    else:
        return {"semaforo": "🔴", "titolo": "NESSUNA INVERSIONE", "colore": TH["chart"]["down"], "operazione": "🚫 Non entrare. Il titolo non mostra ancora segnali di inversione. La discesa potrebbe continuare."}


def render_analisi_decelerazione(ticker, df_total, key_prefix):
    rows = df_total[df_total["Ticker"] == ticker]
    if rows.empty:
        return
    row = rows.iloc[0]

    st.markdown('<div class="decel-inline">', unsafe_allow_html=True)

    c_top, c_spacer = st.columns([1, 6])
    with c_top:
        if st.button("✖ Chiudi analisi", key=f"decel_close_{key_prefix}"):
            st.session_state["decel_ticker"] = None
            st.rerun()

    hist = get_hist_for_ticker(ticker)
    if hist is None or hist.empty:
        st.warning(f"Impossibile scaricare i dati storici per {ticker}.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    fig_decel = grafico_decelerazione(hist, ticker)
    if not fig_decel:
        st.warning("Dati insufficienti per generare il grafico.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    st.plotly_chart(fig_decel, use_container_width=True)

    raw_bs = row.get('Bottom Score (0-4)', 0)
    try:
        bottom_score = int(float(str(raw_bs)))
    except (ValueError, TypeError):
        bottom_score = 0
    bottom_dettagli = str(row.get('Bottom Dettagli', 'Nessun segnale'))
    dd_val = row.get('Drawdown (%)', 'N/D')
    health_val = row.get('Health', 'N/D')
    interpretazione = interpreta_bottom_score(bottom_score, bottom_dettagli)
    score_pct = min(int((bottom_score / 4) * 100), 100)
    thresholds = [(25, TH["chart"]["down"], '🔴 Nessuna inversione'), (50, '#f97316', '🟠 Esaurimento vendita'), (75, TH["chart"]["zone"], '🟡 Segnali iniziali'), (100, TH["chart"]["up"], '🟢 Pronto a invertire')]
    bar_segments = []
    for thr, col, lbl in thresholds:
        filled = score_pct >= thr
        bg = col if filled else TH["bg_base"]; bord = col if filled else TH["border_strong"]; tcol = col if filled else TH["txt3"]
        bar_segments.append('<div style="flex:1;text-align:center;"><div style="height:12px;background:' + bg + ';border-radius:3px;border:1px solid ' + bord + ';margin:0 2px;"></div><div style="font-size:10px;color:' + tcol + ';margin-top:3px;line-height:1.2;">' + lbl + '</div></div>')
    bar_html = ''.join(bar_segments)
    col_border = interpretazione['colore']; semaforo = interpretazione['semaforo']; titolo = interpretazione['titolo']; operazione = interpretazione['operazione']; score_color = interpretazione['colore']
    card_html = ('<div style="background:var(--bg-base);border:1px solid var(--border);border-left:5px solid ' + col_border + ';padding:14px 16px;border-radius:10px;margin-top:10px;">'
        '<div style="display:flex;align-items:center;gap:14px;margin-bottom:10px;"><div style="font-size:28px;">' + semaforo + '</div>'
        '<div style="flex:1;"><div style="font-size:16px;font-weight:800;color:' + score_color + ';font-family:var(--font-head);">' + titolo + '</div>'
        '<div style="font-size:12.5px;color:var(--txt1);margin-top:2px;">' + operazione + '</div></div>'
        '<div style="background:var(--bg-panel);border:1px solid var(--border-strong);padding:6px 14px;border-radius:10px;text-align:center;min-width:76px;"><div style="color:var(--txt3);font-size:10px;text-transform:uppercase;">Score</div>'
        '<div style="color:' + score_color + ';font-weight:800;font-size:22px;line-height:1.1;">' + str(bottom_score) + '<span style="font-size:13px;color:var(--txt3);">/4</span></div></div></div></div>'
        '<div style="margin-bottom:6px;"><div style="font-size:10px;color:var(--txt3);margin-bottom:4px;text-transform:uppercase;letter-spacing:0.05em;">Termometro di inversione</div>'
        '<div style="display:flex;gap:0;">' + bar_html + '</div></div>'
        '<div style="margin-top:10px;font-size:12px;color:var(--txt2);border-top:1px solid var(--border);padding-top:8px;">🔍 <b>Segnali attivi:</b> ' + html.escape(bottom_dettagli) + '</div>'
        '<div style="font-size:11.5px;color:var(--txt3);margin-top:3px;">📊 Drawdown: ' + str(dd_val) + '% &nbsp;|&nbsp; Health: ' + str(health_val) + '</div></div>')
    st.markdown(card_html, unsafe_allow_html=True)
    legenda_html = ('<div style="background:var(--bg-base);border:1px solid var(--border);border-radius:8px;padding:12px 16px;margin-top:8px;font-size:12px;color:var(--txt2);display:grid;grid-template-columns:1fr 1fr;gap:10px;">'
        '<div><b style="color:var(--txt1);">① Prezzo &amp; POC</b><br>Sfondo <span style="color:' + TH["chart"]["up"] + ';">verde</span> = discesa rallenta; <span style="color:' + TH["chart"]["down"] + ';">rosso</span> = prosegue. ▲ = crossover velocità. POC: <span style="color:' + TH["chart"]["poc_strong"] + ';">■ strutturale</span>, <span style="color:' + TH["chart"]["poc_mid"] + ';">■ medio</span>, <span style="color:' + TH["chart"]["poc_min"] + ';">■ minore</span>.</div>'
        '<div><b style="color:var(--txt1);">② Velocità di Discesa</b><br>Linea <span style="color:' + TH["chart"]["roc"] + ';">fucsia</span> sopra lo zero e fuori dalla zona <span style="color:' + TH["chart"]["zone"] + ';">gialla ⚡</span> = decelerazione confermata.</div></div>')
    st.markdown(legenda_html, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------
# RIGA NATIVA (testo completo, niente tagli)
# ---------------------------------------------------------------
_COL_WIDTHS = [1.2, 0.8, 0.8, 0.7, 0.7, 0.7, 1.8, 1.0, 0.8, 0.9, 0.8, 0.8, 0.9, 1.4, 0.8, 0.4]
_HEADER_LABELS = ["Ticker", "Indice", "Prezzo", "DD%", "Health", "Bottom", "Segnali", "POC", "dPOC%", "VWAP", "dVWAP%", "🎯", "MCap", "Operazione", "Stato", "TW"]


def render_riga_screening(row, key_prefix):
    ticker = str(row["Ticker"])
    is_selected = st.session_state.get("decel_ticker") == ticker

    cols_row = st.columns(_COL_WIDTHS)

    btn_type = "primary" if is_selected else "secondary"
    if cols_row[0].button(f"📊 {ticker}", key=f"{key_prefix}_{ticker}", use_container_width=True, type=btn_type):
        if is_selected:
            st.session_state["decel_ticker"] = None
        else:
            st.session_state["decel_ticker"] = ticker
        st.rerun()

    cols_row[1].markdown(f'<div class="cell-txt">{html.escape(str(row.get("Indice", "")))}</div>', unsafe_allow_html=True)
    cols_row[2].markdown(f'<div class="cell-num">{_fmt2(row.get("Prezzo"))}</div>', unsafe_allow_html=True)
    cols_row[3].markdown(f'<div class="cell-num" style="color:{TH["chart"]["down"]};">{_fmt2(row.get("Drawdown (%)"))}</div>', unsafe_allow_html=True)

    health_score = row.get("Health_Score")
    if health_score is not None and not pd.isna(health_score):
        try:
            cols_row[4].markdown(_health_div(int(health_score), str(row.get('Health')).strip()), unsafe_allow_html=True)
        except (ValueError, TypeError):
            cols_row[4].markdown('<div class="cell-muted">—</div>', unsafe_allow_html=True)
    else:
        cols_row[4].markdown('<div class="cell-muted">—</div>', unsafe_allow_html=True)

    bs = row.get("Bottom Score (0-4)")
    try:
        bsf = float(bs)
    except (TypeError, ValueError):
        bsf = None
    if bsf is not None and not pd.isna(bsf):
        cols_row[5].markdown(_bottom_div(bsf), unsafe_allow_html=True)
    else:
        cols_row[5].markdown('<div class="cell-muted">—</div>', unsafe_allow_html=True)

    # SEGNALE COMPLETO, senza troncamenti
    cols_row[6].markdown(f'<div class="det-full">{html.escape(str(row.get("Bottom Dettagli", "—")))}</div>', unsafe_allow_html=True)
    cols_row[7].markdown(f'<div class="cell-num">{html.escape(str(row.get("POC più vicino", "—")))}</div>', unsafe_allow_html=True)
    cols_row[8].markdown(f'<div class="cell-num">{html.escape(str(row.get("Distanza POC (%)", "—")))}</div>', unsafe_allow_html=True)

    vwap_val = row.get("VWAP vicino")
    try:
        vwap_f = float(vwap_val)
    except (TypeError, ValueError):
        vwap_f = 0.0
    if vwap_f and vwap_f > 0:
        tf = str(row.get("_vwap_tf", ""))
        cols_row[9].markdown(f'<div class="cell-num">{vwap_f:.2f}<span style="font-size:10px;color:var(--txt3);"> {html.escape(tf)}</span></div>', unsafe_allow_html=True)
    else:
        cols_row[9].markdown('<div class="cell-muted">—</div>', unsafe_allow_html=True)

    cols_row[10].markdown(f'<div class="cell-num">{html.escape(str(row.get("Distanza VWAP (%)", "—")))}</div>', unsafe_allow_html=True)
    cols_row[11].markdown(_alert_cell(row.get("🎯 Alert", ""), row), unsafe_allow_html=True)
    cols_row[12].markdown(f'<div class="cell-num">{_fmt2(row.get("Market Cap (B)"))}</div>', unsafe_allow_html=True)
    cols_row[13].markdown(_entry_cell(row.get("Entry Mode")), unsafe_allow_html=True)
    cols_row[14].markdown(_stato_cell(row.get("Stato")), unsafe_allow_html=True)

    tw_url = str(row.get("Grafico TW", ""))
    if tw_url and tw_url != "nan":
        cols_row[15].markdown(f"<a href='{html.escape(tw_url, quote=True)}' target='_blank' style='text-decoration:none;font-size:17px;'>📈</a>", unsafe_allow_html=True)
    else:
        cols_row[15].markdown('<div class="cell-muted">—</div>', unsafe_allow_html=True)


def render_tabella_nativa(df, key_prefix, df_total):
    cols_header = st.columns(_COL_WIDTHS)
    for col, label in zip(cols_header, _HEADER_LABELS):
        col.markdown(f'<div class="hdr">{label}</div>', unsafe_allow_html=True)
    for _, row in df.iterrows():
        ticker = str(row["Ticker"])
        render_riga_screening(row, key_prefix)
        if st.session_state.get("decel_ticker") == ticker:
            render_analisi_decelerazione(ticker, df_total, key_prefix)


# ---------------------------------------------------------------
# CORPO
# ---------------------------------------------------------------
st.subheader("📋 Lista Titoli Screening")
st.caption("⚖️ **Operazione Potenziale** è una lettura automatica del metodo REA, non un consiglio: decisione e rischio interamente a carico dell'utente.")
is_all_selected = (indice_scelto == "🌍 TUTTI GLI INDICI INSIEME")

if is_all_selected:
    saved_data = []
    for k, v in st.session_state["screener_database"].items():
        if k != "🌍 TUTTI GLI INDICI INSIEME" and isinstance(v, list):
            for item in v:
                if "Indice" not in item or item["Indice"] == "🌍 TUTTI GLI INDICI INSIEME":
                    item["Indice"] = k
            saved_data.extend(v)
    conteggio = st.session_state.get("scan_count_all", None)
else:
    saved_data = st.session_state["screener_database"].get(indice_scelto, [])
    conteggio = st.session_state.get(f"scan_count_{indice_scelto}", None)

if conteggio is not None:
    st.success(f"Analisi completata su **{conteggio}** titoli.")
elif saved_data and not is_all_selected:
    st.info(f"📂 Dati del run automatico (o ultimo screening) su **{indice_scelto}**.")
elif saved_data and is_all_selected:
    st.info("🌍 Vista Globale Attiva: Fusione di tutti i mercati.")

if st.session_state.get("ultimi_spostamenti"):
    with st.expander("🔔 RILEVATI SPOSTAMENTI DI REGIME!", expanded=True):
        for msg in st.session_state["ultimi_spostamenti"]:
            st.markdown(f"- {msg}")

ordine_colonne = [
    "Ticker", "Indice", "Prezzo", "Drawdown (%)",
    "Health", "Bottom Score (0-4)", "Bottom Dettagli",
    "POC più vicino", "Distanza POC (%)", "VWAP vicino", "Distanza VWAP (%)",
    "🎯 Alert", "Market Cap (B)", "Entry Mode", "Stato"
]

has_data_to_show = (isinstance(saved_data, list) and len(saved_data) > 0)

if has_data_to_show:
    df_total = pd.DataFrame(saved_data)
    for col in ordine_colonne:
        if col not in df_total.columns:
            df_total[col] = "N/D"
    if "Grafico TW" not in df_total.columns:
        df_total["Grafico TW"] = df_total["Ticker"].apply(genera_url_tradingview)
    df_total = arricchisci(df_total, soglia_poc_pct)
    df_total = df_total.drop_duplicates(subset=["Ticker"], keep="last").reset_index(drop=True)

    t_sconto, t_poc = st.tabs(["🔥 AZIENDE IN SCONTO (Health)", "🎯 ALERT POC / VWAP"])

    with t_sconto:
        st.subheader("Titoli in forte sconto")
        df_attivi = df_total[df_total["Stato"] == "Active"].copy()
        if not df_attivi.empty:
            scol, sasc = render_sort_bar("sconto", "Bottom")
            df_attivi = _apply_sort(df_attivi, scol, sasc)
            render_tabella_nativa(df_attivi, "tkbtn_s", df_total)
        else:
            st.info("💡 Nessun titolo in forte sconto trovato.")

    with t_poc:
        st.subheader(f"Titoli con prezzo dentro una zona POC, oppure entro ±{soglia_poc_pct:.1f}% da un POC o VWAP")
        df_poc = df_total[df_total["🎯 Alert"].fillna("").astype(str).str.strip() != ""].copy()
        if not df_poc.empty:
            pcol, pasc = render_sort_bar("poc", "dPOC%")
            df_poc = _apply_sort(df_poc, pcol, pasc)
            render_tabella_nativa(df_poc, "tkbtn_p", df_total)
        else:
            st.info("💡 Nessun titolo attualmente in zona POC / VWAP.")

    st.markdown("---")
else:
    st.info(f"📊 Nessun dato disponibile per '{indice_scelto}'. Il run automatico delle 21:30 UTC popola questa tabella; premi 'AVVIA SCREENING QUALITY (v2)' per un giro manuale immediato.")
