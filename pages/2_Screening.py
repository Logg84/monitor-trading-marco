import streamlit as st
import pandas as pd
import yfinance as yf
import json
import os
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

.block-container { padding-top: 1.5rem; padding-bottom: 1rem; padding-left: 2rem; padding-right: 2rem; max-width: 100%; }

h1 { font-size: 1.6rem !important; margin-bottom: 0.2rem !important; letter-spacing: -0.02em; }
.stTabs { margin-top: -0.2rem; }

.state-change-banner {
    padding: 10px 15px; border-radius: 8px; margin-bottom: 15px;
    border-left: 6px solid #fbbf24; background-color: #1e293b;
    border: 1px solid #334155; color: #f8fafc;
    transition: box-shadow .25s ease;
}
.state-change-banner:hover { box-shadow: 0 6px 22px -10px rgba(251,191,36,.5); }

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

div[data-testid="stButton"] button { transition: all .15s ease; }

.argo-report {
    background: linear-gradient(135deg, #0f172a 0%, #13203a 100%);
    border: 1px solid #1e3a5f; border-left: 5px solid #38bdf8;
    border-radius: 10px; padding: 14px 18px; margin: 4px 0 18px 0;
    box-shadow: 0 8px 30px -18px rgba(56,189,248,.45);
}
.argo-report .ar-head {
    font-family: 'IBM Plex Mono', monospace; font-size: 11px; font-weight: 600;
    letter-spacing: .12em; text-transform: uppercase; color: #38bdf8; margin-bottom: 10px;
}
.argo-report .ar-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.argo-report .ar-chip {
    background: #0b1220; border: 1px solid #243049; border-radius: 8px;
    padding: 7px 12px; min-width: 92px; text-align: left;
    transition: transform .15s ease, border-color .2s ease, box-shadow .2s ease;
}
.argo-report .ar-chip:hover { transform: translateY(-2px); border-color: #38bdf8; box-shadow: 0 6px 18px -10px rgba(56,189,248,.6); }
.argo-report .ar-num { font-family: 'IBM Plex Mono', monospace; font-size: 22px; font-weight: 700; line-height: 1; }
.argo-report .ar-lab { font-size: 9.5px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: #7c8aa3; margin-top: 4px; }
.argo-report .ar-note { font-size: 12.5px; color: #cbd5e1; line-height: 1.5; }
.argo-report .ar-note b { color: #f8fafc; }
.argo-report .ar-add { color: #22c55e; }
.argo-report .ar-upd { color: #60a5fa; }
.argo-report .ar-vw { color: #38bdf8; }
.argo-report .ar-rm { color: #f59e0b; }
</style>
""", unsafe_allow_html=True)

st.title("🎛️ Terminale ARGO × Metodo Rea")

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


def add_debug(msg, level="info"):
    engine.add_debug(msg, level)
    st.session_state["debug_log"] = engine.debug_log


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


def pulisci_auto_zombie(indice: str, ticker_correnti_set: set) -> int:
    df_wl = carica_watchlist_da_github()
    if df_wl.empty:
        return 0
    tag = f"({indice})"
    idx_da_togliere = []
    for idx, row in df_wl.iterrows():
        origine = str(row.get("Origine", "")).strip().lower()
        auto_idx = str(row.get("Auto_Indice", "")).strip()
        nota_poc = str(row.get("Nota POC 1", "")) + str(row.get("Nota POC", ""))
        is_mine = (auto_idx == indice) or (origine == "auto" and tag in nota_poc)
        if origine == "auto" and is_mine:
            if str(row["Ticker"]).strip().upper() not in ticker_correnti_set:
                idx_da_togliere.append(idx)
    if idx_da_togliere:
        df_wl = df_wl.drop(idx_da_togliere)
        commit_csv_su_github(df_wl)
    return len(idx_da_togliere)


macro_info = engine.ottieni_bussola_argo()
macro_data = {"df": macro_info["df"], "latest": macro_info["latest"]}
latest = macro_info["latest"]
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
    color_map_hex = {
        "emerald": "#10b981", "rose": "#f43f5e", "amber": "#f59e0b",
        "indigo": "#6366f1", "orange": "#f97316", "slate": "#64748b"
    }
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

listino_opzioni = ["🌍 TUTTI GLI INDICI INSIEME", "S&P 500", "NASDAQ 100", "DAX (Germania)", "CAC 40 (Francia)", "FTSE MIB (Italia)"]

with st.sidebar:
    st.header("⚙️ Configurazione Metodo REA")
    indice_scelto = st.selectbox("Seleziona l'Indice da Scansionare:", listino_opzioni)
    st.markdown("---")
    default_cap = 10.0 if indice_scelto in ["S&P 500", "NASDAQ 100", "🌍 TUTTI GLI INDICI INSIEME"] else 2.5
    min_market_cap = st.number_input("Market Cap Minima (Miliardi): ", value=default_cap, step=0.5) * 1e9
    soglia_drawdown = st.number_input("Soglia Minima di Drawdown dall'ATH (%) ", value=25.0, step=5.0)
    st.markdown("---")
    soglia_poc_pct = st.number_input("Soglia Vicinanza al POC (%) ", value=2.0, step=0.5, help="Segnala il titolo se il prezzo attuale è entro questa percentuale da un POC ancorato")
    st.markdown("---")
    soglia_promo_pct = st.number_input(
        "Soglia promozione auto in watchlist (%) ", value=2.5, step=0.5,
        help="Un titolo ENTRA da solo in watchlist (🤖) se il prezzo è entro questa % da POC o VWAP. Una volta dentro resta finché è in sconto e i suoi VWAP si rinfrescano a ogni run. I manuali non vengono mai toccati su Livelli/POC."
    )
    st.markdown("---")
    st.caption("💡  Quality Score (0-4):  solidità rispetto alla media del suo indice.")
    st.caption("📉  Bottom Score (0-4):  segnali di inversione (Decelerazione ROC, MACD, POC, Volume).")
    st.caption("🧹  POC operativi:  nel grafico vedi solo i POC entro il " + f"{MAX_POC_DIST_PCT:.0f}% dal prezzo.")
    st.caption("🤖  Automazione:  i titoli in zona entrano da soli; i VWAP si rinfrescano sempre; escono solo se non più in sconto.")
    st.caption("⏰  Screening automatico:  1 volta/giorno alle 21:30 UTC. AVVIA = override manuale.")

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
    if st.button("🚀 AVVIA SCREENING QUALITY (v2)", type="primary"):
        engine.debug_log = []
        st.session_state["debug_log"] = []
        st.session_state["ultimi_spostamenti"] = []
        st.session_state["ultimo_report_auto"] = None
        total_spostamenti = []
        total_count = 0
        tot_agg, tot_upd, tot_vw, tot_zomb = 0, 0, 0, 0
        tot_in_zona = 0

        if indice_scelto == "🌍 TUTTI GLI INDICI INSIEME":
            indices_to_scan = ["S&P 500", "NASDAQ 100", "DAX (Germania)", "CAC 40 (Francia)", "FTSE MIB (Italia)"]
        else:
            indices_to_scan = [indice_scelto]

        for idx_name in indices_to_scan:
            with st.spinner(f"Scansione in corso per {idx_name}..."):
                result_list, spost = engine.perform_screening(
                    idx_name, min_market_cap, soglia_drawdown, soglia_poc_pct
                )
                if result_list:
                    total_spostamenti.extend(spost)
                    total_count += len(result_list)
                    st.session_state[f"scan_count_{idx_name}"] = len(result_list)
                else:
                    st.session_state[f"scan_count_{idx_name}"] = 0
                st.session_state["scan_timestamps"][idx_name] = datetime.datetime.now()
                st.session_state[f"has_scanned_{idx_name}"] = True

                df_scr = pd.DataFrame(result_list) if result_list else pd.DataFrame()
                stats = promuovi_auto_da_screener(df_scr, idx_name, soglia_trigger_pct=soglia_promo_pct)
                tot_agg += stats.get("aggiunti", 0)
                tot_upd += stats.get("aggiornati", 0)
                tot_vw += stats.get("vwappati", 0)
                tot_in_zona += stats.get("in_zona", 0)
                ticker_correnti = set(str(t).strip().upper() for t in df_scr["Ticker"]) if (not df_scr.empty and "Ticker" in df_scr.columns) else set()
                tot_zomb += pulisci_auto_zombie(idx_name, ticker_correnti)

        st.session_state["ultimi_spostamenti"] = total_spostamenti
        st.session_state["scan_count_all"] = total_count
        st.session_state["ultimo_report_auto"] = {
            "aggiunti": tot_agg, "aggiornati": tot_upd, "vwappati": tot_vw,
            "rimossi": tot_zomb, "in_zona": tot_in_zona, "soglia": soglia_promo_pct,
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
        f'<div class="ar-chip"><div class="ar-num ar-add">{rep["aggiunti"]}</div><div class="ar-lab">➕ Aggiunti 🤖</div></div>'
        f'<div class="ar-chip"><div class="ar-num ar-upd">{rep["aggiornati"]}</div><div class="ar-lab">🔄 Auto aggiornati</div></div>'
        f'<div class="ar-chip"><div class="ar-num ar-vw">{rep["vwappati"]}</div><div class="ar-lab">🔃 VWAP rinfrescati</div></div>'
        f'<div class="ar-chip"><div class="ar-num ar-rm">{rep["rimossi"]}</div><div class="ar-lab">🗑️ Usciti (no sconto)</div></div>'
        f'<div class="ar-chip"><div class="ar-num" style="color:#e2e8f0">{rep["in_zona"]}</div><div class="ar-lab">🎯 In zona (≤{soglia_rep:g}%)</div></div>'
    )
    if rep["in_zona"] == 0:
        nota = (f"Nessun titolo dello screening toccava un POC o un VWAP entro ±{soglia_rep:g}%: "
                f"<b>niente nuovi ingressi</b>. I VWAP dei titoli già in watchlist (in sconto) sono stati comunque rinfrescati.")
    else:
        parti = []
        if rep["aggiunti"]:
            parti.append(f"<span class='ar-add'><b>{rep['aggiunti']}</b> nuovi 🤖</span>")
        if rep["aggiornati"]:
            parti.append(f"<span class='ar-upd'><b>{rep['aggiornati']}</b> auto aggiornati</span>")
        if rep["vwappati"]:
            parti.append(f"<span class='ar-vw'><b>{rep['vwappati']}</b> manuali con VWAP rinfrescati</span>")
        nota = f"Esito: {' · '.join(parti)}." if parti else f"<b>{rep['in_zona']}</b> titoli in zona, nessun cambiamento di stato."
    extra = ""
    if rep["rimossi"]:
        extra = f" <span class='ar-rm'>🗑️ {rep['rimossi']}</span> auto rimossi perché non più in sconto."

    st.markdown(
        '<div class="argo-report">'
        '<div class="ar-head">🤖 Automazione watchlist — esito dell\'ultimo screening</div>'
        '<div class="ar-chips">' + chips + '</div>'
        '<div class="ar-note">' + nota + extra + '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------
# ANALISI ATTORI
# ---------------------------------------------------------------
def analizza_attori(latest, df_plot):
    spot = latest["spot"]
    vix = latest["vix"]
    vvx = latest["vvx"]
    rapporto = latest["rapporto"]
    flip = latest["flip"]
    upper = df_plot["Upper_Barrier"].iloc[-1] if "Upper_Barrier" in df_plot else spot * 1.05
    lower = df_plot["Lower_Barrier"].iloc[-1] if "Lower_Barrier" in df_plot else spot * 0.95
    mid = (upper + lower) / 2
    dist_from_mid = (spot - mid) / (upper - lower) if (upper - lower) != 0 else 0

    actors = {}
    if vvx < 90:
        actors["Istituzionale"] = {"emoji": "🏦", "status": "Coperture dormienti", "color": "🟢", "score": 1, "desc": "Flusso neutrale. Nessuna protezione massiccia in atto."}
    elif 90 <= vvx <= 105:
        actors["Istituzionale"] = {"emoji": "🏦", "status": "Allerta graduale", "color": "🟡", "score": 0, "desc": "Prudenza in aumento. Monitorare l'evoluzione."}
    else:
        actors["Istituzionale"] = {"emoji": "🏦", "status": "Panico / Coperture", "color": "🔴", "score": -1, "desc": "Coperture massive in atto. Rischio di crollo."}
    if dist_from_mid < -0.7:
        actors["Market Maker"] = {"emoji": "📊", "status": "Long Gamma", "color": "🟢", "score": 1, "desc": "Supporto solido sotto. Difendono i minimi."}
    elif dist_from_mid > 0.7:
        actors["Market Maker"] = {"emoji": "📊", "status": "Short Gamma", "color": "🔴", "score": -1, "desc": "Resistenza forte sopra. Frenano i rialzi."}
    else:
        actors["Market Maker"] = {"emoji": "📊", "status": "Neutrali", "color": "🟡", "score": 0, "desc": "Posizionamento bilanciato. Nessun estremo."}
    if vix > 25:
        actors["Retail"] = {"emoji": "🧑‍", "status": "Paura (Vendita)", "color": "🔴", "score": -1, "desc": "Panico retail. Minimi di mercato (contrarian buy)."}
    elif vix < 15:
        actors["Retail"] = {"emoji": "🧑‍", "status": "Euforia (Acquisto)", "color": "🟢", "score": 1, "desc": "Euforia retail. Massimi di mercato (contrarian sell)."}
    else:
        actors["Retail"] = {"emoji": "🧑‍", "status": "Neutrale", "color": "🟡", "score": 0, "desc": "Sentiment in attesa."}
    if vix < 18 and rapporto < 5:
        actors["Produttore"] = {"emoji": "🏭", "status": "Buyback Window", "color": "🟢", "score": 1, "desc": "Capitale a basso costo. Emissioni/buyback favorevoli."}
    elif vix > 22 or rapporto > 7:
        actors["Produttore"] = {"emoji": "🏭", "status": "Window Chiusa", "color": "🔴", "score": -1, "desc": "Costo del capitale alto. Stop alle emissioni."}
    else:
        actors["Produttore"] = {"emoji": "🏭", "status": "Neutrale", "color": "🟡", "score": 0, "desc": "Condizioni miste."}
    if spot >= flip:
        actors["Trend Macro"] = {"emoji": "🌍", "status": "Trend Following", "color": "🟢", "score": 1, "desc": "Mercato premia i trend. Momento positivo."}
    else:
        actors["Trend Macro"] = {"emoji": "🌍", "status": "Mean Reversion", "color": "🔴", "score": -1, "desc": "Mercato premia i rimbalzi. Attenzione ai supporti."}
    if vix < 18:
        actors["Gestore Rischio"] = {"emoji": "🎯", "status": "Rischio Controllato", "color": "🟢", "score": 1, "desc": "De-risking in attesa. Flusso stabile."}
    elif 18 <= vix <= 22:
        actors["Gestore Rischio"] = {"emoji": "🎯", "status": "Soglia Allerta", "color": "🟡", "score": 0, "desc": "Monitoraggio. Possibile riduzione esposizione."}
    else:
        actors["Gestore Rischio"] = {"emoji": "🎯", "status": "De-risking Attivo", "color": "🔴", "score": -1, "desc": "Pressione al ribasso sistemica. Vendita forzata."}

    scores = [v["score"] for v in actors.values()]
    avg_score = sum(scores) / len(scores)
    composite_score = int(((avg_score + 1) / 2) * 100)

    retail_score = actors["Retail"]["score"]
    inst_score = actors["Istituzionale"]["score"]
    mm_score = actors["Market Maker"]["score"]
    macro_score = actors["Trend Macro"]["score"]
    risk_score = actors["Gestore Rischio"]["score"]

    sintesi = ""
    if retail_score == 1 and inst_score == -1:
        sintesi = "⚠️ **ALLARME TOP**: Il retail è euforico (VIX < 15) ma le istituzioni si stanno coprendo massicciamente (VVIX > 105). Scenario tipico di un top di breve/medio termine. **Valutare riduzione dell'esposizione o hedging.**"
    elif retail_score == -1 and mm_score == 1:
        sintesi = "✅ **OPPORTUNITÀ BOTTOM**: Il retail sta vendendo per paura (VIX > 25) ma i Market Maker sono long gamma e difendono il supporto. Tipico setup da rimbalzo. **Iniziare ad accumulare gradualmente.**"
    elif macro_score == 1 and risk_score == -1:
        sintesi = "⚡ **CONFLITTO TREND/RISCHIO**: Il trend macro è positivo, ma il gestore del rischio sta riducendo l'esposizione (VIX > 22). Il mercato potrebbe subire scossoni improvvisi. **Mantenere le posizioni ma allargare gli stop loss.**"
    elif avg_score >= 0.5 and macro_score == 1 and inst_score >= 0 and mm_score >= 0:
        sintesi = "📈 **TREND CONFORTEVOLE**: Istituzionali, Market Maker e Trend Macro sono allineati sul rialzo. Il quadro è costruttivo. **Mantenere le posizioni e valutare eventuali aggiunte sui ritracciamenti.**"
    elif avg_score <= -0.5 and macro_score == -1:
        sintesi = "⛔ **RISCHIO SISTEMICO**: Trend macro negativo, gestori del rischio in de-risking e istituzioni coperte. **Evitare nuovi ingressi. Proteggere il capitale.**"
    elif -0.3 < avg_score < 0.3:
        sintesi = "🔍 **MERCATO LATERALE/CONTRASTATO**: I segnali sono misti. **Attendere una convergenza tra i diversi attori prima di prendere posizioni direzionali.**"
    else:
        if avg_score > 0:
            sintesi = f"📊 **LEGGERO BIAS POSITIVO** (Score: {composite_score}/100). Il quadro generale è costruttivo ma non unanime. **Privilegiare ingressi selettivi sui titoli di qualità.**"
        else:
            sintesi = f"📊 **LEGGERO BIAS NEGATIVO** (Score: {composite_score}/100). Il quadro generale è cauto. **Privilegiare la prudenza e attendere segnali più forti.**"

    return actors, composite_score, sintesi

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
        p["poc_price"] = float(p["poc_price"])
        p["weight_norm"] = float(p.get("weight_norm", 5.0))
        p["dist_pct"] = round((price_now - p["poc_price"]) / p["poc_price"] * 100, 2)

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, row_heights=[0.65, 0.35], vertical_spacing=0.06,
        subplot_titles=(
            f"{ticker} — Prezzo & POC operativi (≤{MAX_POC_DIST_PCT:.0f}% dal prezzo)",
            "🌡️ Velocità di Discesa (ROC smoothed) — verde = decelerazione in corso",
        )
    )

    fig.add_trace(go.Scatter(
        x=df.index, y=df['Close'], mode='lines', name='Prezzo',
        line=dict(color='#e2e8f0', width=2.5),
        hovertemplate='<b>%{x|%d %b %Y}</b><br>Prezzo: %{y:.2f}<extra></extra>'
    ), row=1, col=1)

    for i in range(1, len(df)):
        color = 'rgba(34,197,94,0.12)' if roc_rising.iloc[i] else 'rgba(239,68,68,0.10)'
        fig.add_vrect(x0=df.index[i-1], x1=df.index[i], fillcolor=color, opacity=1, layer="below", line_width=0, row=1, col=1)

    for p in pocs:
        if abs(p["dist_pct"]) > MAX_POC_DIST_PCT:
            continue
        wn = float(p.get("weight_norm", 5.0))
        poc_price = float(p["poc_price"])
        if wn >= 8:
            lcolor, lwidth, dash = '#ef4444', 2.5, 'solid'
        elif wn >= 5:
            lcolor, lwidth, dash = '#f97316', 1.8, 'dash'
        else:
            lcolor, lwidth, dash = '#64748b', 1.0, 'dot'
        importance_label = "🔴 STRUTTURALE" if wn >= 8 else ("🟠 MEDIO" if wn >= 5 else "⚫ MINORE")
        fig.add_hline(
            y=poc_price, line=dict(color=lcolor, width=lwidth, dash=dash), opacity=0.85,
            annotation_text=f"POC {p['anchor_year']} | {poc_price:.2f} | {importance_label} (peso {wn:.0f}/10)",
            annotation_position="top right", annotation_font=dict(size=9, color=lcolor), row=1, col=1
        )

    for i in range(1, len(roc_smoothed)):
        if (not pd.isna(roc_smoothed.iloc[i]) and not pd.isna(roc_smoothed.iloc[i-1])
                and roc_smoothed.iloc[i-1] < 0 and roc_smoothed.iloc[i] >= 0):
            fig.add_trace(go.Scatter(
                x=[df.index[i]], y=[df['Close'].iloc[i]], mode='markers+text',
                marker=dict(symbol='triangle-up', size=14, color='#22c55e', line=dict(color='white', width=1)),
                text=["↑ ROC+"], textposition="top center", textfont=dict(size=9, color='#22c55e'),
                name='Segnale ROC+', showlegend=False,
                hovertemplate=f'<b>Crossover ROC positivo</b><br>{df.index[i].strftime("%d %b %Y")}<extra></extra>'
            ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=roc_smoothed.index, y=roc_smoothed, mode='lines', name='Velocità discesa',
        line=dict(color='#a78bfa', width=2), fill='tozeroy', fillcolor='rgba(167,139,250,0.15)',
        hovertemplate='<b>%{x|%d %b %Y}</b><br>Velocità: %{y:.1f}%<extra></extra>'
    ), row=2, col=1)
    fig.add_hline(y=0, line_dash="solid", line_color="#475569", opacity=0.8, row=2, col=1)
    fig.add_hrect(
        y0=-5, y1=5, fillcolor="rgba(250,204,21,0.08)",
        line=dict(color="rgba(250,204,21,0.3)", width=1, dash="dot"),
        annotation_text="⚡ Zona inversione (±5%)", annotation_position="top right",
        annotation_font=dict(size=9, color="#fbbf24"), row=2, col=1
    )

    fig.update_layout(
        template="plotly_dark", height=620, margin=dict(l=0, r=0, t=45, b=0),
        hovermode='x unified', showlegend=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(15,23,42,1)',
    )
    fig.update_yaxes(title_text="Prezzo", row=1, col=1, color='#94a3b8', gridcolor='#1e222d')
    fig.update_yaxes(title_text="Velocità (%)", row=2, col=1, color='#94a3b8', gridcolor='#1e222d', zeroline=False)
    fig.update_xaxes(gridcolor='#1e222d', row=1, col=1)
    fig.update_xaxes(title_text="Data", gridcolor='#1e222d', row=2, col=1)
    return fig

# ---------------------------------------------------------------
# INTERPRETAZIONE BOTTOM SCORE
# ---------------------------------------------------------------
def interpreta_bottom_score(score, dettagli):
    if score == 4:
        return {"semaforo": "🟢", "titolo": "FORTE INVERSIONE", "colore": "#22c55e", "operazione": "✅ Pronto per l'ingresso. Il titolo è tecnicamente pronto a ripartire. Valutare l'acquisto con stop loss sotto il POC."}
    elif score == 3:
        return {"semaforo": "🟡", "titolo": "SEGNALI INIZIALI", "colore": "#eab308", "operazione": "🔍 Monitoraggio. La decelerazione è iniziata, ma manca ancora la conferma del volume o del POC."}
    elif score == 2:
        return {"semaforo": "🟡", "titolo": "ESAURIMENTO VENDITA", "colore": "#eab308", "operazione": "⏳ Pazienza. La discesa sta rallentando, ma non ci sono ancora segnali di acquisto attivi."}
    else:
        return {"semaforo": "🔴", "titolo": "NESSUNA INVERSIONE", "colore": "#ef4444", "operazione": "🚫 Non entrare. Il titolo non mostra ancora segnali di inversione. La discesa potrebbe continuare."}

# ---------------------------------------------------------------
# TAB 1 — REGIME ARGO
# ---------------------------------------------------------------
tab1, tab2 = st.tabs(["📈 Analisi Regime ARGO", "📋 Screening e Titoli"])

with tab1:
    df_plot = macro_data["df"].copy()
    df_plot['Rolling_Std'] = df_plot['SPX'].rolling(window=20, min_periods=1).std()
    df_plot['Upper_Barrier'] = df_plot['Flip_Line'] + (2 * df_plot['Rolling_Std'])
    df_plot['Lower_Barrier'] = df_plot['Flip_Line'] - (2 * df_plot['Rolling_Std'])

    st.subheader("🔍 Sala di Controllo Multi-Attore")
    actors, composite_score, sintesi = analizza_attori(latest, df_plot)

    col_sint1, col_sint2 = st.columns([3, 1])
    with col_sint1:
        if composite_score >= 60:
            bg_color, border_color = "rgba(34, 197, 94, 0.15)", "#22c55e"
        elif composite_score >= 40:
            bg_color, border_color = "rgba(234, 179, 8, 0.15)", "#eab308"
        else:
            bg_color, border_color = "rgba(239, 68, 68, 0.15)", "#ef4444"
        st.markdown(f"""
        <div style="background-color: {bg_color}; border-left: 5px solid {border_color}; padding: 12px 15px; border-radius: 8px; margin-bottom: 10px;">
            <div style="font-size: 14px; font-weight: 500; color: #f8fafc;">{sintesi}</div>
            <div style="font-size: 11px; color: #94a3b8; margin-top: 5px;">
                🕒 Aggiornato: {datetime.datetime.now().strftime('%H:%M:%S')} | Composite Score: {composite_score}/100
            </div>
        </div>
        """, unsafe_allow_html=True)
    with col_sint2:
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number", value=composite_score, domain={'x': [0, 1], 'y': [0, 1]},
            gauge={'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "white"}, 'bar': {'color': "#fbbf24"},
                   'steps': [{'range': [0, 40], 'color': "rgba(239, 68, 68, 0.4)"}, {'range': [40, 60], 'color': "rgba(234, 179, 8, 0.4)"}, {'range': [60, 100], 'color': "rgba(34, 197, 94, 0.4)"}],
                   'threshold': {'line': {'color': "white", 'width': 4}, 'thickness': 0.75, 'value': composite_score}},
            title={'text': "<b>Rischio / Rendimento</b>", 'font': {'size': 14}}
        ))
        fig_gauge.update_layout(template="plotly_dark", height=150, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig_gauge, use_container_width=True)

    st.markdown("### 📌 Prospettive dei Singoli Attori")
    actor_keys = ["Istituzionale", "Market Maker", "Retail", "Produttore", "Trend Macro", "Gestore Rischio"]
    cols = st.columns(3)
    for i, key in enumerate(actor_keys):
        actor = actors[key]
        col = cols[i % 3]
        color_text = {"🟢": "#a7f3d0", "🟡": "#fde68a", "🔴": "#fca5a5"}.get(actor["color"], "#f8fafc")
        with col:
            st.markdown(f"""
            <div class="actor-box" style="border-left: 3px solid {color_text};">
                <div class="emoji">{actor['emoji']}</div>
                <div class="label">{key}</div>
                <div class="value" style="color: {color_text};">{actor['color']} {actor['status']}</div>
                <div class="desc">{actor['desc']}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("📊 Dettaglio Tecnico (Dati Grezzi)")
    col_chart1, col_chart2 = st.columns([2, 1])
    with col_chart1:
        fig1 = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.08, subplot_titles=(None, "Protezioni Attive nel Mercato (VVIX)"))
        fig1.add_trace(go.Scatter(x=df_plot["Date"], y=df_plot["SPX"], mode='lines', name='S&P 500', line=dict(color='#60a5fa', width=2.5)), row=1, col=1)
        fig1.add_trace(go.Scatter(x=df_plot["Date"], y=df_plot["Flip_Line"], mode='lines', name='Flip Line (MA 20)', line=dict(color='#fbbf24', width=2, dash='dash')), row=1, col=1)
        fig1.add_trace(go.Scatter(x=df_plot["Date"], y=df_plot["Upper_Barrier"], mode='lines', name='Barriera Sup (+2σ)', line=dict(color='#f87171', width=1.5, dash='dot')), row=1, col=1)
        fig1.add_trace(go.Scatter(x=df_plot["Date"], y=df_plot["Lower_Barrier"], mode='lines', name='Barriera Inf (-2σ)', line=dict(color='#34d399', width=1.5, dash='dot')), row=1, col=1)
        fig1.add_trace(go.Scatter(x=pd.concat([df_plot["Date"], df_plot["Date"][::-1]]), y=pd.concat([df_plot["Upper_Barrier"], df_plot["Lower_Barrier"][::-1]]), fill='toself', fillcolor='rgba(148, 163, 184, 0.15)', line=dict(color='rgba(255,255,255,0)'), showlegend=False, hoverinfo='skip'), row=1, col=1)
        gamma_color = 'rgba(34, 197, 94, 0.15)' if argo_bussola['bias'] == 'LONG' else 'rgba(239, 68, 68, 0.15)'
        fig1.add_trace(go.Scatter(x=pd.concat([df_plot["Date"], df_plot["Date"][::-1]]), y=pd.concat([df_plot["SPX"], df_plot["Flip_Line"][::-1]]), fill='toself', fillcolor=gamma_color, line=dict(color='rgba(255,255,255,0)'), showlegend=False, hoverinfo='skip'), row=1, col=1)
        last_date = df_plot["Date"].iloc[-1]
        last_spx = df_plot["SPX"].iloc[-1]
        last_flip = df_plot["Flip_Line"].iloc[-1]
        fig1.add_annotation(x=last_date, y=last_spx, text=f"S&P {last_spx:.2f}", showarrow=True, arrowhead=1, arrowcolor='#60a5fa', row=1, col=1, bgcolor='rgba(15, 23, 42, 0.8)', font=dict(color='#60a5fa', size=11))
        fig1.add_annotation(x=last_date, y=last_flip, text=f"Flip {last_flip:.2f}", showarrow=True, arrowhead=1, arrowcolor='#fbbf24', row=1, col=1, bgcolor='rgba(15, 23, 42, 0.8)', font=dict(color='#fbbf24', size=11))
        fig1.add_trace(go.Bar(x=df_plot["Date"], y=df_plot["VVIX"], name='VVIX (Coperture)', marker_color='rgba(244, 114, 182, 0.7)', marker_line_color='rgba(244, 114, 182, 1)', marker_line_width=0.5), row=2, col=1)
        fig1.add_hline(y=105, line_dash="dash", line_color="#ef4444", opacity=0.9, row=2, col=1, annotation_text="⚡ ALLERTA (105)", annotation_position="top right")
        fig1.add_hline(y=90, line_dash="dash", line_color="#94a3b8", opacity=0.5, row=2, col=1, annotation_text="Soglia Controllo", annotation_position="bottom right")
        fig1.update_layout(template="plotly_dark", height=500, margin=dict(l=0, r=0, t=20, b=0), hovermode='x unified', legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10)))
        fig1.update_yaxes(title_text="Prezzo S&P 500", row=1, col=1, color='#94a3b8')
        fig1.update_yaxes(title_text="VVIX", row=2, col=1, color='#94a3b8')
        fig1.update_xaxes(title_text="Data", row=2, col=1)
        st.plotly_chart(fig1, use_container_width=True)
        st.caption("""
        **📖 Legenda:** Linea blu = S&P 500 · gialla tratteggiata = Flip Line (SMA20) · punteggiate = barriere ±2σ · area verde/rossa = gamma (sopra la Flip = trend positivo) · istogramma rosa = VVIX (sopra 105 = coperture istituzionali in allarme).
        """)
    with col_chart2:
        ratio_val = argo_bussola['rapporto']
        if ratio_val < 5.0:
            gauge_color, status_text = "#94a3b8", "⚡ MOLLA PRONTA"
        elif 5.0 <= ratio_val <= 7.0:
            gauge_color, status_text = "#22c55e", "📈 TREND IDEALE"
        else:
            gauge_color, status_text = "#ef4444", "🌪️ SCOSSONI ESTREMI"
        fig2 = go.Figure(go.Indicator(mode="gauge+number+delta", value=ratio_val, domain={'x': [0, 1], 'y': [0, 1]}, delta={'reference': 6.0, 'valueformat': '.2f'}, gauge={'axis': {'range': [0, 10], 'tickwidth': 1, 'tickcolor': "white"}, 'bar': {'color': gauge_color}, 'steps': [{'range': [0, 4.9], 'color': "rgba(148, 163, 184, 0.2)"}, {'range': [5.0, 7.0], 'color': "rgba(34, 197, 94, 0.3)"}, {'range': [7.1, 10], 'color': "rgba(239, 68, 68, 0.2)"}], 'threshold': {'line': {'color': "white", 'width': 4}, 'thickness': 0.75, 'value': ratio_val}}, title={'text': f"<b>{status_text}</b><br><span style='font-size:12px; color:#94a3b8;'>VVIX / VIX</span>"}))
        fig2.update_layout(template="plotly_dark", height=350, margin=dict(l=20, r=20, t=50, b=20))
        st.plotly_chart(fig2, use_container_width=True)
        st.caption("**📖 Termometro:** < 5.0 = molla (accumulo) · 5.0–7.0 = trend ideale · > 7.0 = scossoni (rischio).")

    st.subheader("🧠 Volatilità Istituzionale: VIX vs VVIX")
    fig3 = make_subplots(specs=[[{"secondary_y": True}]])
    fig3.add_trace(go.Scatter(x=df_plot["Date"], y=df_plot["VIX"], name="VIX (Volatilità Implicita)", line=dict(color="#60a5fa", width=2)), secondary_y=False)
    fig3.add_trace(go.Scatter(x=df_plot["Date"], y=df_plot["VVIX"], name="VVIX (Volatilità del VIX)", line=dict(color="#f472b6", width=2, dash='dot')), secondary_y=True)
    fig3.add_hline(y=105, line_dash="dash", line_color="#ef4444", opacity=0.5, secondary_y=True, annotation_text="ALLERTA 105")
    fig3.add_hline(y=90, line_dash="dash", line_color="#94a3b8", opacity=0.3, secondary_y=True)
    fig3.update_layout(template="plotly_dark", height=300, margin=dict(l=0, r=0, t=40, b=0), hovermode='x unified')
    fig3.update_yaxes(title_text="VIX", secondary_y=False)
    fig3.update_yaxes(title_text="VVIX", secondary_y=True)
    st.plotly_chart(fig3, use_container_width=True)
    st.caption("💡 VVIX > 105 con VIX < 25 = falso segnale di calma: le istituzioni si stanno già coprendo (anticipo di crollo).")

# ---------------------------------------------------------------
# TAB 2 — SCREENING
# ---------------------------------------------------------------
with tab2:
    st.subheader("📋 Lista Titoli Screening")
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

    configurazione_colonne = {
        "Grafico TW": st.column_config.LinkColumn("Grafico TW", help="Apri su TradingView", display_text="📈 Apri"),
        "Prezzo": st.column_config.NumberColumn("Prezzo", format="%.2f"),
        "Drawdown (%)": st.column_config.NumberColumn("Drawdown (%)", format="%.2f"),
        "Size Suggerita (%)": st.column_config.NumberColumn("Size Suggerita (%)", format="%.2f"),
        "Market Cap (B)": st.column_config.NumberColumn("Market Cap (B)", format="%.2f"),
    }
    ordine_colonne = [
        "Ticker", "Indice", "Prezzo", "Drawdown (%)",
        "Quality Score (0-4)", "Bottom Score (0-4)", "Bottom Dettagli",
        "Size Suggerita (%)", "Entry Mode",
        "Market Cap (B)", "POC più vicino", "Distanza POC (%)", "🎯 ALERT POC", "Stato"
    ]

    def color_quality(val):
        if isinstance(val, (int, float)):
            if val >= 3:
                return 'background-color: #065f46; color: #a7f3d0; font-weight: bold;'
            elif val >= 2:
                return 'background-color: #1a3a2a; color: #86efac; font-weight: bold;'
            else:
                return 'background-color: #7f1d1d; color: #fca5a5; font-weight: bold;'
        return ''

    def color_bottom(val):
        if isinstance(val, (int, float)):
            if val >= 4:
                return 'background-color: #065f46; color: #a7f3d0; font-weight: bold;'
            elif val >= 3:
                return 'background-color: #1a3a2a; color: #86efac; font-weight: bold;'
            elif val >= 2:
                return 'background-color: #78350f; color: #fde68a; font-weight: bold;'
            else:
                return 'background-color: #7f1d1d; color: #fca5a5; font-weight: bold;'
        return ''

    def apply_style(df):
        if df.empty:
            return df
        return df.style.map(color_quality, subset=['Quality Score (0-4)']).map(color_bottom, subset=['Bottom Score (0-4)'])

    has_data_to_show = (isinstance(saved_data, list) and len(saved_data) > 0)

    if has_data_to_show:
        df_total = pd.DataFrame(saved_data)
        for col in ordine_colonne:
            if col not in df_total.columns:
                df_total[col] = "N/D"
        if "Grafico TW" not in df_total.columns:
            df_total["Grafico TW"] = df_total["Ticker"].apply(genera_url_tradingview)

        t_sconto, t_poc = st.tabs(["🔥 AZIENDE IN SCONTO (Quality)", "🎯 ALERT POC"])
        with t_sconto:
            st.subheader("Titoli in forte sconto - ordinati per Bottom Score")
            df_attivi = df_total[df_total["Stato"] == "Active"].sort_values(by="Bottom Score (0-4)", ascending=False)
            if not df_attivi.empty:
                styled_df = apply_style(df_attivi[ordine_colonne + ["Grafico TW"]])
                st.dataframe(styled_df, use_container_width=True, hide_index=True, column_config=configurazione_colonne)
            else:
                st.info("💡 Nessun titolo in forte sconto trovato.")
        with t_poc:
            st.subheader(f"Titoli con prezzo entro ±{soglia_poc_pct:.1f}% da un POC affidabile")
            df_poc = df_total[df_total["🎯 ALERT POC"] == "🎯 SU POC"].copy()
            if not df_poc.empty:
                styled_df = apply_style(df_poc[ordine_colonne + ["Grafico TW"]])
                st.dataframe(styled_df, use_container_width=True, hide_index=True, column_config=configurazione_colonne)
            else:
                st.info("💡 Nessun titolo attualmente in zona POC affidabile.")

        st.markdown("---")
        st.subheader("📉 Analisi di Decelerazione per Singolo Titolo")
        ticker_list = sorted(df_total["Ticker"].unique())
        if ticker_list:
            selected_ticker = st.selectbox("Seleziona un titolo per visualizzare il grafico di decelerazione:", ticker_list)
            if selected_ticker:
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

                hist = get_hist_for_ticker(selected_ticker)
                if hist is not None and not hist.empty:
                    fig_decel = grafico_decelerazione(hist, selected_ticker)
                    if fig_decel:
                        st.plotly_chart(fig_decel, use_container_width=True)
                        row = df_total[df_total["Ticker"] == selected_ticker].iloc[0]
                        raw_bs = row.get('Bottom Score (0-4)', 0)
                        try:
                            bottom_score = int(float(str(raw_bs)))
                        except (ValueError, TypeError):
                            bottom_score = 0
                        bottom_dettagli = str(row.get('Bottom Dettagli', 'Nessun segnale'))
                        dd_val = row.get('Drawdown (%)', 'N/D')
                        qs_val = row.get('Quality Score (0-4)', 'N/D')
                        interpretazione = interpreta_bottom_score(bottom_score, bottom_dettagli)

                        score_pct = int((bottom_score / 4) * 100)
                        thresholds = [
                            (25, '#ef4444', '🔴 Nessuna inversione'),
                            (50, '#f97316', '🟠 Esaurimento vendita'),
                            (75, '#eab308', '🟡 Segnali iniziali'),
                            (100, '#22c55e', '🟢 Pronto a invertire'),
                        ]
                        bar_segments = []
                        for thr, col, lbl in thresholds:
                            filled = score_pct >= thr
                            bg = col if filled else '#1e293b'
                            bord = col if filled else '#334155'
                            tcol = col if filled else '#94a3b8'
                            bar_segments.append(
                                '<div style="flex:1;text-align:center;">'
                                '<div style="height:12px;background:' + bg + ';border-radius:3px;'
                                'border:1px solid ' + bord + ';margin:0 2px;"></div>'
                                '<div style="font-size:9px;color:' + tcol + ';margin-top:3px;line-height:1.2;">' + lbl + '</div>'
                                '</div>'
                            )
                        bar_html = ''.join(bar_segments)
                        col_border = interpretazione['colore']
                        semaforo = interpretazione['semaforo']
                        titolo = interpretazione['titolo']
                        operazione = interpretazione['operazione']
                        score_color = interpretazione['colore']
                        card_html = (
                            '<div style="background-color:#0f172a;border-left:5px solid ' + col_border + ';'
                            'padding:14px 16px;border-radius:8px;margin-top:10px;">'
                            '<div style="display:flex;align-items:center;gap:14px;margin-bottom:10px;">'
                            '<div style="font-size:26px;">' + semaforo + '</div>'
                            '<div style="flex:1;">'
                            '<div style="font-size:15px;font-weight:700;color:' + score_color + ';">' + titolo + '</div>'
                            '<div style="font-size:12px;color:#f8fafc;margin-top:2px;">' + operazione + '</div>'
                            '</div>'
                            '<div style="background:#1e293b;padding:6px 14px;border-radius:10px;text-align:center;min-width:72px;">'
                            '<div style="color:#94a3b8;font-size:10px;text-transform:uppercase;">Score</div>'
                            '<div style="color:' + score_color + ';font-weight:800;font-size:22px;line-height:1.1;">'
                            + str(bottom_score) +
                            '<span style="font-size:13px;color:#64748b;">/4</span>'
                            '</div>'
                            '</div>'
                            '</div>'
                            '<div style="margin-bottom:6px;">'
                            '<div style="font-size:10px;color:#64748b;margin-bottom:4px;text-transform:uppercase;letter-spacing:0.05em;">Termometro di inversione</div>'
                            '<div style="display:flex;gap:0;">' + bar_html + '</div>'
                            '</div>'
                            '<div style="margin-top:10px;font-size:11px;color:#94a3b8;border-top:1px solid #1e293b;padding-top:8px;">'
                            '🔍 <b>Segnali attivi:</b> ' + bottom_dettagli +
                            '</div>'
                            '<div style="font-size:11px;color:#64748b;margin-top:3px;">'
                            '📊 Drawdown: ' + str(dd_val) + '% &nbsp;|&nbsp; Quality Score: ' + str(qs_val) + '/4'
                            '</div>'
                            '</div>'
                        )
                        st.markdown(card_html, unsafe_allow_html=True)
                        legenda_html = (
                            '<div style="background:#0f172a;border:1px solid #1e293b;border-radius:6px;'
                            'padding:10px 14px;margin-top:8px;font-size:11px;color:#94a3b8;">'
                            '<b style="color:#e2e8f0;">📖 Come leggere i pannelli:</b><br>'
                            '<b style="color:#e2e8f0;">① Prezzo &amp; POC</b> — Sfondo verde = la discesa sta rallentando; '
                            'rosso = la discesa prosegue. Il triangolo ▲ verde segna il crossover della velocità. '
                            'Sono tracciate SOLO le linee POC operative (entro il ' + f'{MAX_POC_DIST_PCT:.0f}% dal prezzo): i relitti storici sono esclusi. '
                            'Linee POC: '
                            '<span style="color:#ef4444;">■ rosso = strutturale</span>, '
                            '<span style="color:#f97316;">■ arancio = medio</span>, '
                            '<span style="color:#64748b;">■ grigio = minore</span>.<br>'
                            '<b style="color:#e2e8f0;">② Velocità di Discesa</b> — Quando la linea viola sale '
                            'sopra lo zero ed esce dalla zona gialla ⚡, la decelerazione è confermata.'
                            '</div>'
                        )
                        st.markdown(legenda_html, unsafe_allow_html=True)
                    else:
                        st.warning("Dati insufficienti per generare il grafico.")
                else:
                    st.warning(f"Impossibile scaricare i dati storici per {selected_ticker}.")
        else:
            st.info("Nessun titolo disponibile per l'analisi.")
    else:
        st.info(f"📊 Nessun dato disponibile per '{indice_scelto}'. Il run automatico delle 21:30 UTC popola questa tabella; premi 'AVVIA SCREENING QUALITY (v2)' per un giro manuale immediato.")
