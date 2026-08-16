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

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=IBM+Plex+Mono:wght@400;600&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.block-container { padding-top: 1.5rem; padding-bottom: 1rem; padding-left: 1.25rem; padding-right: 1.25rem; max-width: 100%; }
h1 { font-size: 1.6rem !important; margin-bottom: 0.2rem !important; letter-spacing: -0.02em; }
div[data-testid="stButton"] button { transition: all .15s ease; }

section[data-testid="stSidebar"] { width: 250px !important; min-width: 250px !important; }
section[data-testid="stSidebar"] > div { width: 250px !important; }

.argo-report {
    position: relative; overflow: hidden;
    background: linear-gradient(135deg, #0f172a 0%, #13203a 100%);
    border: 1px solid #1e3a5f; border-left: 5px solid #38bdf8;
    border-radius: 10px; padding: 16px 18px; margin: 4px 0 18px 0;
    box-shadow: 0 8px 30px -18px rgba(56,189,248,.45);
}
.argo-report::before {
    content: ""; position: absolute; inset: 0;
    background: radial-gradient(600px 120px at 0% 0%, rgba(56,189,248,.10), transparent 70%);
    pointer-events: none;
}
.argo-report .ar-head { position: relative; font-family: 'IBM Plex Mono', monospace; font-size: 11px; font-weight: 600; letter-spacing: .12em; text-transform: uppercase; color: #38bdf8; margin-bottom: 12px; }
.argo-report .ar-chips { position: relative; display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.argo-report .ar-chip { background: #0b1220; border: 1px solid #243049; border-radius: 8px; padding: 7px 12px; min-width: 92px; text-align: left; transition: transform .15s ease, border-color .2s ease, box-shadow .2s ease; }
.argo-report .ar-chip:hover { transform: translateY(-2px); border-color: #38bdf8; box-shadow: 0 6px 18px -10px rgba(56,189,248,.6); }
.argo-report .ar-num { font-family: 'IBM Plex Mono', monospace; font-size: 22px; font-weight: 700; line-height: 1; }
.argo-report .ar-lab { font-size: 9.5px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: #7c8aa3; margin-top: 4px; }
.argo-report .ar-note { position: relative; font-size: 12.5px; color: #cbd5e1; line-height: 1.5; }
.argo-report .ar-note b { color: #f8fafc; }
.argo-report .ar-add { color: #22c55e; }
.argo-report .ar-upd { color: #60a5fa; }
.argo-report .ar-vw { color: #38bdf8; }
.argo-report .ar-rm { color: #f59e0b; }
.argo-report .ar-tags { position: relative; margin-top: 14px; padding-top: 12px; border-top: 1px solid #1e293b; display: flex; flex-direction: column; gap: 9px; }
.argo-report .ar-group { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.argo-report .ar-glabel { font-family: 'IBM Plex Mono', monospace; font-size: 10px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; margin-right: 2px; }
.argo-report .ar-tag { font-family: 'IBM Plex Mono', monospace; font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 999px; border: 1px solid transparent; background: #0b1220; cursor: default; transition: transform .15s ease, box-shadow .2s ease, border-color .2s ease, background .2s ease; }
.argo-report .ar-tag:hover { transform: translateY(-2px) scale(1.04); box-shadow: 0 6px 16px -10px rgba(56,189,248,.7); }
.argo-report .ar-tag.ar-add { color: #86efac; border-color: rgba(34,197,94,.45); background: rgba(34,197,94,.10); }
.argo-report .ar-tag.ar-add:hover { border-color: #22c55e; }
.argo-report .ar-tag.ar-upd { color: #93c5fd; border-color: rgba(96,165,250,.45); background: rgba(96,165,250,.10); }
.argo-report .ar-tag.ar-upd:hover { border-color: #60a5fa; }
.argo-report .ar-tag.ar-vw { color: #67e8f9; border-color: rgba(56,189,248,.45); background: rgba(56,189,248,.10); }
.argo-report .ar-tag.ar-vw:hover { border-color: #38bdf8; }
.argo-report .ar-tag.ar-rm { color: #fca5a5; border-color: rgba(239,68,68,.45); background: rgba(239,68,68,.10); }
.argo-report .ar-tag.ar-rm:hover { border-color: #ef4444; }
.argo-report .ar-tag.ar-tag-more { color: #7c8aa3; border-color: #243049; }

/* ---- barra ordinamento ---- */
.sk-cap { font-family: 'IBM Plex Mono', monospace; font-size: 10px; letter-spacing: .12em; text-transform: uppercase; color: #64748b; margin: 2px 0 6px 0; }
div[data-testid="stHorizontalBlock"] div[data-testid="stButton"] button { padding: 5px 4px !important; font-size: 11px !important; font-family: 'IBM Plex Mono', monospace !important; }

/* ---- tabella screening ---- */
.argo-tbl-wrap { max-height: 74vh; overflow: auto; border: 1px solid #1e293b; border-radius: 12px; background: #0a0f1a; box-shadow: inset 0 1px 0 rgba(255,255,255,.02); }
.argo-tbl-wrap::-webkit-scrollbar { width: 10px; height: 10px; }
.argo-tbl-wrap::-webkit-scrollbar-track { background: transparent; }
.argo-tbl-wrap::-webkit-scrollbar-thumb { background: #243049; border-radius: 8px; border: 2px solid #0a0f1a; }
.argo-tbl-wrap::-webkit-scrollbar-thumb:hover { background: #334155; }
.argo-tbl-wrap::-webkit-scrollbar-corner { background: #0a0f1a; }
.argo-tbl { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 12px; }
.argo-tbl thead th {
    position: sticky; top: 0; z-index: 3; background: #0b1220; color: #7c8aa3;
    font-family: 'IBM Plex Mono', monospace; font-size: 10px; letter-spacing: .06em;
    text-transform: uppercase; padding: 11px 10px; text-align: left;
    border-bottom: 1px solid #243049; white-space: nowrap;
}
.argo-tbl thead th.r { text-align: right; }
.argo-tbl thead th.c { text-align: center; }
.argo-tbl tbody td {
    padding: 9px 10px; border-bottom: 1px solid #141d2e; color: #cbd5e1;
    vertical-align: middle; white-space: nowrap; transition: background .12s ease, color .12s ease;
}
.argo-tbl tbody tr:nth-child(even) td { background: rgba(255,255,255,.018); }
.argo-tbl tbody tr:hover td { background: rgba(56,189,248,.14) !important; color: #f8fafc !important; }
.argo-tbl thead th:first-child, .argo-tbl tbody td:first-child { position: sticky; left: 0; z-index: 2; }
.argo-tbl thead th:first-child { z-index: 4; background: #0b1220; box-shadow: 2px 0 6px -2px rgba(0,0,0,.6); }
.argo-tbl tbody td:first-child { background: #0a0f1a; box-shadow: 2px 0 6px -2px rgba(0,0,0,.5); }
.argo-tbl tbody tr:nth-child(even) td:first-child { background: #0d1320; }
.argo-tbl tbody tr:hover td:first-child { background: rgba(56,189,248,.14) !important; box-shadow: inset 3px 0 0 #38bdf8, 2px 0 6px -2px rgba(0,0,0,.5); }
.argo-tbl td.r { text-align: right; }
.argo-tbl td.c { text-align: center; }
.argo-tbl td.num { font-family: 'IBM Plex Mono', monospace; }
.argo-tbl td.tk { font-family: 'IBM Plex Mono', monospace; font-weight: 600; color: #f1f5f9; }
.argo-tbl td.idx { color: #7c8aa3; font-size: 11px; }
.argo-tbl td.dd { color: #fca5a5; }
.argo-tbl td.muted { color: #475569; }
.argo-tbl td.det { max-width: 360px; white-space: normal; line-height: 1.35; color: #94a3b8; }
.argo-tbl td.score { text-align: center; font-family: 'IBM Plex Mono', monospace; font-weight: 700; }
.argo-tbl .tf { font-size: 9px; color: #64748b; margin-left: 4px; font-family: 'IBM Plex Mono', monospace; }
.argo-tbl .sub { display: block; font-size: 9.5px; color: #94a3b8; margin-top: 3px; font-family: 'IBM Plex Mono', monospace; letter-spacing: .02em; }
.argo-tbl .pill { display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 10.5px; font-weight: 600; white-space: nowrap; }
.argo-tbl a.tw { text-decoration: none; font-size: 14px; filter: grayscale(.2); transition: transform .12s ease, filter .12s ease; display: inline-block; }
.argo-tbl a.tw:hover { transform: scale(1.25); filter: none; }
.argo-tbl a.tklink { color: #7dd3fc; text-decoration: none; font-weight: 700; transition: color .12s ease; }
.argo-tbl a.tklink:hover { color: #f8fafc; text-decoration: underline; }
</style>
""", unsafe_allow_html=True)

render_navbar("screening", hide_sidebar=False)
section_header("Terminale operativo", "Screening & Titoli in Sconto")

# ---------- LEGENDA HEALTH CHECK ----------
with st.expander("ℹ️ Legenda Health Check", expanded=False):
    st.markdown("""
    **Health Check** – Valutazione assoluta della salute finanziaria (0-4):
    - 🔹 **Free Cash Flow** TTM > 0 → l'azienda genera cassa operativa
    - 🔹 **Crescita Ricavi** YoY (ultimo trimestre vs stesso trimestre anno prima) > 0 → fatturato in espansione
    - 🔹 **Utile Netto** ultimo anno fiscale > 0 → redditività positiva
    - 🔹 **Debito / Patrimonio Netto** < 1.5 → indebitamento contenuto

    | Punteggio | Simbolo | Significato |
    |-----------|---------|-------------|
    | 4/4 | ✅ | Tutti i criteri superati – azienda solida |
    | 2-3/4 | ⚠️ | Qualche debolezza – attenzione |
    | 0-1/4 | ❌ | Criteri largamente non soddisfatti – fragile |

    **Nota per i mercati europei**  
    Le small cap europee possono mostrare fisiologicamente D/E più elevati o FCF negativo per investimenti.  
    Un punteggio di 2‑3/4 ⚠️ in questi casi non è di per sé un segnale di debolezza: va letto nel contesto della capitalizzazione e del settore.
    """)

# ---------------------------------------------------------------
# MOTORE
# ---------------------------------------------------------------
if "engine" not in st.session_state:
    st.session_state["engine"] = DataEngine()
engine = st.session_state["engine"]

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


macro_info = engine.ottieni_bussola_argo()
argo_bussola = macro_info["bussola"]


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

if st.session_state.get("argo_state_changed", False):
    old_stato = st.session_state.get("argo_old_stato", "N/D")
    new_stato = st.session_state.get("argo_new_stato", "N/D")
    old_color = st.session_state.get("argo_old_color", "slate")
    new_color = st.session_state.get("argo_new_color", "slate")
    color_map_hex = {"emerald": "#10b981", "rose": "#f43f5e", "amber": "#f59e0b", "indigo": "#6366f1", "orange": "#f97316", "slate": "#64748b"}
    st.markdown(f"""
    <div class="state-change-banner" style="border-left-color: {color_map_hex.get(new_color, '#fbbf24')};">
        <strong>⚠️ CAMBIO REGIME RILEVATO!</strong> <br>
        <span style="color: {color_map_hex.get(old_color, '#94a3b8')};"><b>{old_stato}</b></span>
        ➜
        <span style="color: {color_map_hex.get(new_color, '#fbbf24')};"><b>{new_stato}</b></span>
    </div>
    """, unsafe_allow_html=True)

color_map = {"emerald": "#10b981", "rose": "#f43f5e", "amber": "#f59e0b", "indigo": "#6366f1", "orange": "#f97316", "slate": "#64748b"}
st.markdown(f"""
<div style="background-color: #1e293b; border-left: 5px solid {color_map[argo_bussola['color']]}; padding: 6px 12px; border-radius: 6px; margin-bottom: 15px; margin-top: 5px;">
    <div style="display: flex; justify-content: space-between; align-items: center;">
        <div>
            <span style="font-size: 9px; font-weight: bold; text-transform: uppercase; color: #94a3b8;">Direttiva Tattica</span>
            <h5 style="margin: 0; color: #f8fafc; font-weight: 800; font-size: 1.1rem;">{argo_bussola['stato']}</h5>
            <p style="margin: 0; font-size: 11px; color: #cbd5e1; font-weight: 500;">{argo_bussola['desc']}</p>
        </div>
        <div style="background-color: #0f172a; border: 1px solid #334155; padding: 4px 10px; border-radius: 4px; text-align: center;">
            <span style="font-size: 8px; font-weight: bold; color: #64748b; text-transform: uppercase;">BIAS</span>
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
    soglia_poc_pct = st.number_input("Soglia Vicinanza POC / VWAP (%) ", value=2.0, step=0.5, help="Segnala (🎯 Alert) il titolo se il prezzo è dentro una zona POC, oppure entro questa % da un POC o VWAP.")
    st.markdown("---")
    soglia_promo_pct = st.number_input(
        "Soglia promozione auto in watchlist (%) ", value=2.5, step=0.5,
        help="Un titolo ENTRA da solo in watchlist (🤖) se il prezzo è dentro una zona POC, oppure entro questa % da POC o VWAP. Una volta dentro resta finché è in sconto e i suoi VWAP si rinfrescano a ogni run. I manuali non vengono mai toccati su Livelli/POC."
    )
    st.markdown("---")
    st.caption("💡  Health Check (0-4):  valutazione assoluta della salute finanziaria (FCF, Crescita Ricavi, Utile Netto, D/E).")
    st.caption("📉  Bottom Score (0-4):  segnali di inversione (Decelerazione ROC, MACD, POC, Volume).")
    st.caption("🧹  POC operativi:  nel grafico vedi solo i POC entro il " + f"{MAX_POC_DIST_PCT:.0f}% dal prezzo.")
    st.caption("🤖  Automazione:  i titoli in zona entrano da soli; i VWAP si rinfrescano sempre; escono solo se non più in sconto.")
    st.caption("⏰  Screening automatico:  1 volta/giorno alle 21:30 UTC. AVVIA = override manuale.")
    st.caption("⚖️  Operazione Potenziale:  lettura automatica non vincolante. Decisione e rischio sono interamente a carico dell'utente.")
    st.caption("🖱️  Clicca su un ticker in tabella per aprire l'analisi di decelerazione del titolo.")

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
            st.markdown(f"<div style='font-size:11px; color:{color};'>[{entry['time']}] {entry['msg']}</div>", unsafe_allow_html=True)
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
        f'<div class="ar-chip"><div class="ar-num" style="color:#e2e8f0">{rep["in_zona"]}</div><div class="ar-lab">🎯 In zona (≤{soglia_rep:g}%)</div></div>'
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
# ARRICCHIMENTO + RENDERER TABELLA
# ---------------------------------------------------------------
_HDR = {
    "Ticker": ("Ticker", "Clicca per aprire l'analisi di decelerazione"),
    "Indice": ("Indice", "Indice di appartenenza"),
    "Prezzo": ("Prezzo", "Prezzo attuale"),
    "Drawdown (%)": ("DD %", "Drawdown dall'ATH (%)"),
    "Health": ("Health", "Health Check (0-4) — salute finanziaria assoluta"),
    "Bottom Score (0-4)": ("Bottom", "Bottom Score (0-4) — segnali di inversione"),
    "Bottom Dettagli": ("Segnali", "Segnali tecnici attivi"),
    "POC più vicino": ("POC vicino", "POC operativo più vicino"),
    "Distanza POC (%)": ("dPOC %", "📍 in zona se dentro area POC, altrimenti distanza % dal POC più vicino"),
    "VWAP vicino": ("VWAP vicino", "VWAP (3M/1Y/4Y) più vicino al prezzo"),
    "Distanza VWAP (%)": ("dVWAP %", "Distanza % dal VWAP più vicino"),
    "🎯 Alert": ("🎯 Alert", "Tocco POC / VWAP entro la soglia, con distanza"),
    "Market Cap (B)": ("MCap", "Capitalizzazione (miliardi)"),
    "Entry Mode": ("Operazione Potenziale", "Lettura automatica non vincolante del metodo REA: decisione e rischio interamente a carico dell'utente"),
    "Stato": ("Stato", "Stato del titolo"),
    "Grafico TW": ("TW", "Apri su TradingView"),
}
_RIGHT = {"Prezzo", "Drawdown (%)", "Market Cap (B)", "Distanza POC (%)", "VWAP vicino", "Distanza VWAP (%)"}
_CENTER = {"Health", "Bottom Score (0-4)", "🎯 Alert", "Grafico TW", "Stato"}

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


def _esc(v):
    return html.escape("" if v is None else str(v))


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
            if in_zona:
                parts.append("POC 📍 in zona")
            elif pd.notna(dp):
                parts.append(f"POC {dp:+.1f}%")
            else:
                parts.append("POC")
        if vwap_hit:
            parts.append(f"VWAP {dv:+.1f}%")
        if poc_hit and vwap_hit:
            label = "🎯 POC+VWAP"
        elif poc_hit:
            label = "🎯 IN ZONA POC" if in_zona else "🎯 SU POC"
        else:
            label = "🎯 SU VWAP"
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
        return _esc(v)


def _score_bg(col, v):
    if col.startswith("Bottom"):
        if v >= 4: return "background:#065f46;color:#a7f3d0"
        if v >= 3: return "background:#143524;color:#86efac"
        if v >= 2: return "background:#3a2408;color:#fde68a"
        return "background:#3a1414;color:#fca5a5"
    if v >= 3: return "background:#065f46;color:#a7f3d0"
    if v >= 2: return "background:#143524;color:#86efac"
    return "background:#3a1414;color:#fca5a5"


def _pill(text, bg, fg):
    return f'<span class="pill" style="background:{bg};color:{fg}">{html.escape(str(text))}</span>'


def _entry_cell(v):
    s = str(v)
    if s.startswith("🚀"): return _pill(s, "rgba(34,197,94,.16)", "#86efac")
    if s.startswith("⏳"): return _pill(s, "rgba(245,158,11,.16)", "#fcd34d")
    if s.startswith("⛔"): return _pill(s, "rgba(239,68,68,.16)", "#fca5a5")
    if s.startswith("📈"): return _pill(s, "rgba(96,165,250,.16)", "#93c5fd")
    return _pill(s, "rgba(148,163,184,.12)", "#cbd5e1")


def _stato_cell(v):
    s = str(v).strip()
    if s == "Active": return _pill(s, "rgba(34,197,94,.16)", "#86efac")
    if s == "Ripartito": return _pill(s, "rgba(245,158,11,.16)", "#fcd34d")
    if s == "Nuovo": return _pill(s, "rgba(96,165,250,.16)", "#93c5fd")
    return _pill(s or "—", "rgba(148,163,184,.12)", "#94a3b8")


def _alert_cell(val, row):
    label = str(val).strip()
    if not label:
        return '<span class="muted">—</span>'
    detail = str(row.get("_alert_detail", "")).strip() if row is not None else ""
    if "POC+VWAP" in label:
        bg, fg = "rgba(167,139,250,.20)", "#d8b4fe"
    elif "IN ZONA" in label:
        bg, fg = "rgba(34,197,94,.20)", "#86efac"
    elif "SU POC" in label:
        bg, fg = "rgba(244,63,94,.20)", "#fda4af"
    else:
        bg, fg = "rgba(0,180,216,.20)", "#67e8f9"
    inner = _pill(label, bg, fg)
    if detail:
        inner += f'<span class="sub">{html.escape(detail)}</span>'
    return inner


def _health_style(score):
    if score == 4:
        return "background:#065f46; color:#a7f3d0"
    elif score >= 2:
        return "background:#78350f; color:#fde68a"
    else:
        return "background:#7f1d1d; color:#fca5a5"


def _td(col, val, row=None):
    na = _isna(val)
    raw = "" if na else str(val).strip()
    if col == "Ticker":
        if raw:
            inner = f'<a class="tklink" href="?ticker={html.escape(raw, quote=True)}" title="Apri analisi decelerazione">{html.escape(raw)}</a>'
        else:
            inner = "—"
        return ("tk", "", inner)
    if col == "Indice":
        return ("idx", "", html.escape(raw))
    if col == "Grafico TW":
        url = "" if na else str(val)
        inner = f'<a class="tw" href="{html.escape(url, quote=True)}" target="_blank" rel="noopener">📈</a>' if url else "—"
        return ("c", "", inner)
    if col == "Health":
        score = row.get("Health_Score") if row is not None else None
        if score is None or pd.isna(score):
            return ("score", "", "—")
        try:
            score_int = int(score)
        except (ValueError, TypeError):
            return ("score", "", str(val))
        disp = str(val).strip()
        return ("score", _health_style(score_int), disp)
    if col == "Bottom Score (0-4)":
        try:
            v = float(val)
        except Exception:
            v = None
        if v is None or pd.isna(v):
            return ("score", "", "—")
        disp = str(int(v)) if float(v).is_integer() else f"{float(v):.1f}"
        return ("score", _score_bg(col, v), disp)
    if col == "Bottom Dettagli":
        return ("det", "", html.escape(raw) or "—")
    if col == "Entry Mode":
        return ("", "", _entry_cell(val))
    if col == "Stato":
        return ("c", "", _stato_cell(val))
    if col == "🎯 Alert":
        return ("c", "", _alert_cell(val, row))
    if col == "VWAP vicino":
        tf = str(row.get("_vwap_tf", "")).strip() if row is not None else ""
        if na or float(val or 0) == 0:
            return ("r num muted", "", "—")
        return ("r num", "", f'{float(val):.2f}<span class="tf">{html.escape(tf)}</span>')
    if col == "Distanza VWAP (%)":
        if na:
            return ("r num muted", "", "—")
        return ("r num", "", f'{float(val):+.1f}%')
    if col == "Distanza POC (%)":
        if str(val).strip() == "📍 in zona":
            return ("r num", "background:rgba(34,197,94,.20);color:#86efac;font-weight:700", "📍 in zona")
        d = row.get("_dist_poc_num") if row is not None else np.nan
        if d is None or (isinstance(d, float) and pd.isna(d)):
            return ("r num muted", "", "N/D")
        return ("r num", "", f'{float(d):+.1f}%')
    if col == "Prezzo":
        return ("r num", "", _fmt2(val))
    if col == "Market Cap (B)":
        return ("r num", "", _fmt2(val))
    if col == "Drawdown (%)":
        return ("r num dd", "", _fmt2(val))
    if col == "POC più vicino":
        if raw in ("", "nan", "None"):
            return ("num muted", "", "—")
        if raw == "N/D":
            return ("num muted", "", "N/D")
        return ("num", "", html.escape(raw))
    return ("", "", html.escape(raw) or "—")


def _th_class(col):
    if col in _RIGHT: return "r"
    if col in _CENTER: return "c"
    return ""


def _screening_table_html(df, columns):
    head = "".join(
        f'<th class="{_th_class(c)}" title="{html.escape(_HDR.get(c, (c, c))[1], quote=True)}">'
        f'{html.escape(_HDR.get(c, (c, c))[0])}</th>' for c in columns)
    rows = []
    for _, r in df.iterrows():
        cells = []
        for c in columns:
            cls, style, inner = _td(c, r.get(c), r)
            st_attr = f' style="{style}"' if style else ""
            cells.append(f'<td class="{cls}"{st_attr}>{inner}</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return (f'<div class="argo-tbl-wrap"><table class="argo-tbl"><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


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
# GRAFICO DECELERAZIONE
# ---------------------------------------------------------------
def grafico_decelerazione(hist, ticker):
    if hist is None or len(hist) < 30:
        return None
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
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.65, 0.35], vertical_spacing=0.06,
        subplot_titles=(f"{ticker} — Prezzo & POC operativi (≤{MAX_POC_DIST_PCT:.0f}% dal prezzo)",
                        "🌡️ Velocità di Discesa (ROC smoothed) — verde = decelerazione in corso"))
    fig.add_trace(go.Scatter(x=df.index, y=df['Close'], mode='lines', name='Prezzo', line=dict(color='#e2e8f0', width=2.5), hovertemplate='<b>%{x|%d %b %Y}</b><br>Prezzo: %{y:.2f}<extra></extra>'), row=1, col=1)
    for i in range(1, len(df)):
        color = 'rgba(34,197,94,0.12)' if roc_rising.iloc[i] else 'rgba(239,68,68,0.10)'
        fig.add_vrect(x0=df.index[i-1], x1=df.index[i], fillcolor=color, opacity=1, layer="below", line_width=0, row=1, col=1)
    for p in pocs:
        if abs(p["dist_pct"]) > MAX_POC_DIST_PCT:
            continue
        wn = float(p.get("weight_norm", 5.0)); poc_price = float(p["poc_price"])
        if wn >= 8: lcolor, lwidth, dash = '#ef4444', 2.5, 'solid'
        elif wn >= 5: lcolor, lwidth, dash = '#f97316', 1.8, 'dash'
        else: lcolor, lwidth, dash = '#64748b', 1.0, 'dot'
        importance_label = "🔴 STRUTTURALE" if wn >= 8 else ("🟠 MEDIO" if wn >= 5 else "⚫ MINORE")
        fig.add_hline(y=poc_price, line=dict(color=lcolor, width=lwidth, dash=dash), opacity=0.85, annotation_text=f"POC {p['anchor_year']} | {poc_price:.2f} | {importance_label} (peso {wn:.0f}/10)", annotation_position="top right", annotation_font=dict(size=9, color=lcolor), row=1, col=1)
    for i in range(1, len(roc_smoothed)):
        if (not pd.isna(roc_smoothed.iloc[i]) and not pd.isna(roc_smoothed.iloc[i-1]) and roc_smoothed.iloc[i-1] < 0 and roc_smoothed.iloc[i] >= 0):
            fig.add_trace(go.Scatter(x=[df.index[i]], y=[df['Close'].iloc[i]], mode='markers+text', marker=dict(symbol='triangle-up', size=14, color='#22c55e', line=dict(color='white', width=1)), text=["↑ ROC+"], textposition="top center", textfont=dict(size=9, color='#22c55e'), name='Segnale ROC+', showlegend=False, hovertemplate=f'<b>Crossover ROC positivo</b><br>{df.index[i].strftime("%d %b %Y")}<extra></extra>'), row=1, col=1)
    fig.add_trace(go.Scatter(x=roc_smoothed.index, y=roc_smoothed, mode='lines', name='Velocità discesa', line=dict(color='#a78bfa', width=2), fill='tozeroy', fillcolor='rgba(167,139,250,0.15)', hovertemplate='<b>%{x|%d %b %Y}</b><br>Velocità: %{y:.1f}%<extra></extra>'), row=2, col=1)
    fig.add_hline(y=0, line_dash="solid", line_color="#475569", opacity=0.8, row=2, col=1)
    fig.add_hrect(y0=-5, y1=5, fillcolor="rgba(250,204,21,0.08)", line=dict(color="rgba(250,204,21,0.3)", width=1, dash="dot"), annotation_text="⚡ Zona inversione (±5%)", annotation_position="top right", annotation_font=dict(size=9, color="#fbbf24"), row=2, col=1)
    fig.update_layout(template="plotly_dark", height=620, margin=dict(l=0, r=0, t=45, b=0), hovermode='x unified', showlegend=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(15,23,42,1)')
    fig.update_yaxes(title_text="Prezzo", row=1, col=1, color='#94a3b8', gridcolor='#1e222d')
    fig.update_yaxes(title_text="Velocità (%)", row=2, col=1, color='#94a3b8', gridcolor='#1e222d', zeroline=False)
    fig.update_xaxes(gridcolor='#1e222d', row=1, col=1)
    fig.update_xaxes(title_text="Data", gridcolor='#1e222d', row=2, col=1)
    return fig


def interpreta_bottom_score(score, dettagli):
    if score >= 4:
        return {"semaforo": "🟢", "titolo": "FORTE INVERSIONE", "colore": "#22c55e", "operazione": "✅ Pronto per l'ingresso. Il titolo è tecnicamente pronto a ripartire. Valutare l'acquisto con stop loss sotto il POC."}
    elif score == 3:
        return {"semaforo": "🟡", "titolo": "SEGNALI INIZIALI", "colore": "#eab308", "operazione": "🔍 Monitoraggio. La decelerazione è iniziata, ma manca ancora la conferma del volume o del POC."}
    elif score == 2:
        return {"semaforo": "🟡", "titolo": "ESAURIMENTO VENDITA", "colore": "#eab308", "operazione": "⏳ Pazienza. La discesa sta rallentando, ma non ci sono ancora segnali di acquisto attivi."}
    else:
        return {"semaforo": "🔴", "titolo": "NESSUNA INVERSIONE", "colore": "#ef4444", "operazione": "🚫 Non entrare. Il titolo non mostra ancora segnali di inversione. La discesa potrebbe continuare."}


# ---------------------------------------------------------------
# CORPO: LISTA TITOLI SCREENING
# ---------------------------------------------------------------
st.subheader("📋 Lista Titoli Screening")
st.caption("⚖️ **Operazione Potenziale** è una lettura automatica del metodo REA, non un consiglio d'investimento: ogni decisione operativa e il relativo rischio sono interamente a carico dell'utente.")
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

    t_sconto, t_poc = st.tabs(["🔥 AZIENDE IN SCONTO (Health)", "🎯 ALERT POC / VWAP"])

    with t_sconto:
        st.subheader("Titoli in forte sconto")
        df_attivi = df_total[df_total["Stato"] == "Active"].copy()
        if not df_attivi.empty:
            scol, sasc = render_sort_bar("sconto", "Bottom")
            df_attivi = _apply_sort(df_attivi, scol, sasc)
            st.markdown(_screening_table_html(df_attivi, ordine_colonne + ["Grafico TW"]), unsafe_allow_html=True)
        else:
            st.info("💡 Nessun titolo in forte sconto trovato.")

    with t_poc:
        st.subheader(f"Titoli con prezzo dentro una zona POC, oppure entro ±{soglia_poc_pct:.1f}% da un POC o VWAP")
        df_poc = df_total[df_total["🎯 Alert"].fillna("").astype(str).str.strip() != ""].copy()
        if not df_poc.empty:
            pcol, pasc = render_sort_bar("poc", "dPOC%")
            df_poc = _apply_sort(df_poc, pcol, pasc)
            st.markdown(_screening_table_html(df_poc, ordine_colonne + ["Grafico TW"]), unsafe_allow_html=True)
        else:
            st.info("💡 Nessun titolo attualmente in zona POC / VWAP.")

    st.markdown("---")

    # ---------------------------------------------------------------
    # ANALISI DECELERAZIONE A SCOMPARSA (click sul ticker in tabella)
    # ---------------------------------------------------------------
    _sel_tk = str(st.query_params.get("ticker", "") or "").strip().upper()
    ticker_set = set(str(t).strip().upper() for t in df_total["Ticker"].unique())

    if _sel_tk and _sel_tk in ticker_set:
        st.markdown('<div style="margin:2px 0 6px"><a href="?" style="color:#fca5a5;font-size:11px;text-decoration:none">✖ chiudi analisi</a></div>', unsafe_allow_html=True)
        with st.expander(f"📉 Analisi di Decelerazione — {_sel_tk}", expanded=True):
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

            hist = get_hist_for_ticker(_sel_tk)
            if hist is not None and not hist.empty:
                fig_decel = grafico_decelerazione(hist, _sel_tk)
                if fig_decel:
                    st.plotly_chart(fig_decel, use_container_width=True)
                    row = df_total[df_total["Ticker"].str.upper() == _sel_tk].iloc[0]
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
                    thresholds = [(25, '#ef4444', '🔴 Nessuna inversione'), (50, '#f97316', '🟠 Esaurimento vendita'), (75, '#eab308', '🟡 Segnali iniziali'), (100, '#22c55e', '🟢 Pronto a invertire')]
                    bar_segments = []
                    for thr, col, lbl in thresholds:
                        filled = score_pct >= thr
                        bg = col if filled else '#1e293b'; bord = col if filled else '#334155'; tcol = col if filled else '#94a3b8'
                        bar_segments.append('<div style="flex:1;text-align:center;"><div style="height:12px;background:' + bg + ';border-radius:3px;border:1px solid ' + bord + ';margin:0 2px;"></div><div style="font-size:9px;color:' + tcol + ';margin-top:3px;line-height:1.2;">' + lbl + '</div></div>')
                    bar_html = ''.join(bar_segments)
                    col_border = interpretazione['colore']; semaforo = interpretazione['semaforo']; titolo = interpretazione['titolo']; operazione = interpretazione['operazione']; score_color = interpretazione['colore']
                    card_html = ('<div style="background-color:#0f172a;border-left:5px solid ' + col_border + ';padding:14px 16px;border-radius:8px;margin-top:10px;">'
                        '<div style="display:flex;align-items:center;gap:14px;margin-bottom:10px;"><div style="font-size:26px;">' + semaforo + '</div>'
                        '<div style="flex:1;"><div style="font-size:15px;font-weight:700;color:' + score_color + ';">' + titolo + '</div>'
                        '<div style="font-size:12px;color:#f8fafc;margin-top:2px;">' + operazione + '</div></div>'
                        '<div style="background:#1e293b;padding:6px 14px;border-radius:10px;text-align:center;min-width:72px;"><div style="color:#94a3b8;font-size:10px;text-transform:uppercase;">Score</div>'
                        '<div style="color:' + score_color + ';font-weight:800;font-size:22px;line-height:1.1;">' + str(bottom_score) + '<span style="font-size:13px;color:#64748b;">/4</span></div></div></div></div>'
                        '<div style="margin-bottom:6px;"><div style="font-size:10px;color:#64748b;margin-bottom:4px;text-transform:uppercase;letter-spacing:0.05em;">Termometro di inversione</div>'
                        '<div style="display:flex;gap:0;">' + bar_html + '</div></div>'
                        '<div style="margin-top:10px;font-size:11px;color:#94a3b8;border-top:1px solid #1e293b;padding-top:8px;">🔍 <b>Segnali attivi:</b> ' + bottom_dettagli + '</div>'
                        '<div style="font-size:11px;color:#64748b;margin-top:3px;">📊 Drawdown: ' + str(dd_val) + '% &nbsp;|&nbsp; Health: ' + str(health_val) + '</div></div>')
                    st.markdown(card_html, unsafe_allow_html=True)
                    legenda_html = ('<div style="background:#0f172a;border:1px solid #1e293b;border-radius:6px;padding:10px 14px;margin-top:8px;font-size:11px;color:#94a3b8;">'
                        '<b style="color:#e2e8f0;">📖 Come leggere i pannelli:</b><br>'
                        '<b style="color:#e2e8f0;">① Prezzo &amp; POC</b> — Sfondo verde = la discesa sta rallentando; rosso = la discesa prosegue. Il triangolo ▲ verde segna il crossover della velocità. Sono tracciate SOLO le linee POC operative (entro il ' + f'{MAX_POC_DIST_PCT:.0f}% dal prezzo): i relitti storici sono esclusi. Linee POC: <span style="color:#ef4444;">■ rosso = strutturale</span>, <span style="color:#f97316;">■ arancio = medio</span>, <span style="color:#64748b;">■ grigio = minore</span>.<br>'
                        '<b style="color:#e2e8f0;">② Velocità di Discesa</b> — Quando la linea viola sale sopra lo zero ed esce dalla zona gialla ⚡, la decelerazione è confermata.</div>')
                    st.markdown(legenda_html, unsafe_allow_html=True)
                else:
                    st.warning("Dati insufficienti per generare il grafico.")
            else:
                st.warning(f"Impossibile scaricare i dati storici per {_sel_tk}.")
    else:
        st.caption("🖱️ Clicca su un **ticker** in tabella per aprire qui l'analisi di decelerazione del titolo scelto.")
else:
    st.info(f"📊 Nessun dato disponibile per '{indice_scelto}'. Il run automatico delle 21:30 UTC popola questa tabella; premi 'AVVIA SCREENING QUALITY (v2)' per un giro manuale immediato.")
