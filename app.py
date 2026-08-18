import streamlit as st
import pandas as pd
import os
import io
import datetime
import time
import json
import requests
import re
import yfinance as yf
from PIL import Image
import base64
from nav import render_navbar, section_header
from theme import get_theme
from data_engine import DataEngine, zona_poc_effettiva

MAPPA_BORSA_EUROPEA = {"CPR": "CPR.MI", "RI": "RI.PA", "NESN": "NESN.SW", "AF": "AF.PA"}

def storico_yfinance(ticker: str, period: str, interval: str) -> pd.DataFrame:
    simbolo = MAPPA_BORSA_EUROPEA.get(ticker, ticker)
    try:
        h = yf.Ticker(simbolo).history(period=period, interval=interval, auto_adjust=True)
        return h.dropna(subset=["Close"]) if not h.empty else pd.DataFrame()
    except Exception as e:
        print(f"Errore storico yfinance per {simbolo}: {e}")
        return pd.DataFrame()

CSV_PATH = "watchlist.csv"
MODEL_NAME = "qwen/qwen3.6-27b"

st.set_page_config(page_title="Watchlist Grafici", layout="wide", page_icon="📈")

# Inizializza session state per dati pesanti
if "engine" not in st.session_state:
    st.session_state["engine"] = DataEngine()
# Cache watchlist caricata una volta per sessione (refresh dopo modifiche esplicite)
if "watchlist_last_commit" not in st.session_state:
    st.session_state["watchlist_last_commit"] = 0
if "watchlist_cached" not in st.session_state:
    st.session_state["watchlist_cached"] = carica_watchlist()
if "prezzi_sessione" not in st.session_state:
    st.session_state["prezzi_sessione"], st.session_state["prezzi_aggiornati_il"] = carica_prezzi_condivisi()

TH = get_theme()

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

html, body { font-family: 'Inter', system-ui, sans-serif; }

.block-container { padding: 1.5rem 1.5rem 2rem 1.5rem; max-width: 100%; }

h1, h2, h3, h4, h5, h6 { font-family: var(--font-head, 'Inter'), sans-serif; color: var(--txt-1); letter-spacing: -0.01em; }

h3 {
    font-size: 1.1rem !important; font-weight: 700 !important;
    color: var(--accent) !important; text-transform: uppercase;
    letter-spacing: 0.08em !important; margin-top: 0.5rem !important;
}

hr { margin: 1.5rem 0 !important; border-color: var(--border) !important; border-top-width: 1px !important; }

.wl-badge {
    font-family: 'IBM Plex Mono', monospace; font-size: 0.82rem; font-weight: 600;
    padding: 4px 11px; border-radius: 7px; display: inline-block;
    border: 1px solid transparent; white-space: nowrap;
    transition: transform .12s ease, box-shadow .15s ease;
}
.wl-badge:hover { transform: translateY(-1px); }
.wl-badge.l1 { color: var(--fg-l1); background: rgba(251,191,36,0.12); border-color: rgba(251,191,36,0.35); }
.wl-badge.l2 { color: var(--fg-l2); background: rgba(34,197,94,0.12); border-color: rgba(34,197,94,0.35); }
.wl-badge.l3 { color: var(--fg-l3); background: rgba(239,68,68,0.12); border-color: rgba(239,68,68,0.35); }
.wl-badge.v1, .wl-badge.v2, .wl-badge.v3 { color: var(--fg-v); background: rgba(6,182,212,0.12); border-color: rgba(6,182,212,0.35); }
.wl-badge.p1, .wl-badge.p2, .wl-badge.p3 { color: var(--fg-p); background: rgba(167,139,250,0.12); border-color: rgba(167,139,250,0.35); }
.wl-badge.empty { color: var(--fg-empty); background: transparent; border: 1px dashed var(--border-strong); }

.wl-header {
    font-family: 'IBM Plex Mono', monospace; font-size: 0.68rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.1em; color: var(--txt-muted);
    padding-bottom: 6px; border-bottom: 1px solid var(--border); margin-bottom: 4px;
}

div[data-testid="stButton"] button {
    border: 1px solid var(--border-strong); background: var(--bg-panel); color: var(--txt-2);
    border-radius: 7px; font-weight: 500; transition: all 0.15s ease;
}
div[data-testid="stButton"] button:hover {
    border-color: var(--accent); color: var(--accent); background: var(--bg-hover); transform: translateY(-1px);
}

div[data-testid="column"]:nth-of-type(1) div[data-testid="stButton"] button {
    color: var(--txt-1); font-family: 'IBM Plex Mono', monospace; font-weight: 700;
    text-align: left; border: none; background: transparent; padding-left: 0; font-size: 0.92rem;
}
div[data-testid="column"]:nth-of-type(1) div[data-testid="stButton"] button:hover {
    color: var(--accent); background: transparent; border: none;
}

div[data-testid="stFileUploaderDropzone"] {
    border: 1px dashed var(--border-strong); background: var(--bg-panel);
    border-radius: 12px; padding: 1.5rem !important;
    transition: border-color .15s ease, background .15s ease;
}
div[data-testid="stFileUploaderDropzone"]:hover { border-color: var(--accent); background: var(--bg-hover); }

div[data-testid="stInput"] input, div[data-testid="stNumberInput"] input {
    background: var(--bg-panel); border: 1px solid var(--border); color: var(--txt-1);
    font-family: 'IBM Plex Mono', monospace; border-radius: 7px;
}
div[data-testid="stInput"] input:focus, div[data-testid="stNumberInput"] input:focus {
    border-color: var(--accent); box-shadow: 0 0 0 2px rgba(56,189,248,0.18);
}

.wl-card {
    background: linear-gradient(135deg, var(--bg-panel) 0%, var(--bg-panel-2) 100%);
    border: 1px solid var(--border); border-radius: 12px; padding: 16px 18px;
    margin-bottom: 12px; box-shadow: 0 4px 20px -10px rgba(0,0,0,.15);
}
.wl-card-head {
    font-family: 'IBM Plex Mono', monospace; font-size: 10px; font-weight: 700;
    letter-spacing: .12em; text-transform: uppercase; color: var(--accent); margin-bottom: 10px;
}

.wl-price {
    font-family: 'IBM Plex Mono', monospace; font-weight: 700; font-size: 0.95rem;
    color: var(--txt-1); padding: 3px 8px; background: rgba(56,189,248,0.08);
    border-radius: 6px; display: inline-block;
}

.wl-origin {
    display: inline-block; font-family: 'IBM Plex Mono', monospace; font-size: 9px; font-weight: 700;
    letter-spacing: 0.05em; padding: 2px 7px; border-radius: 999px; margin-left: 4px; vertical-align: middle;
}
.wl-origin.auto { color: var(--fg-v); background: rgba(6,182,212,0.15); border: 1px solid rgba(6,182,212,0.35); }
.wl-origin.man { color: var(--fg-origin-man); background: rgba(148,163,184,0.10); border: 1px solid rgba(148,163,184,0.30); }

.wl-ai-box {
    background: linear-gradient(135deg, #1e1b4b 0%, #312e81 100%);
    border: 1px solid #4c1d95; border-left: 4px solid var(--violet, #a78bfa);
    border-radius: 10px; padding: 12px 14px; margin: 10px 0; font-size: 12px; color: #e0e7ff;
}
.wl-ai-box b { color: #c4b5fd; }

.wl-chart-head {
    display: flex; align-items: center; gap: 12px; padding: 8px 14px;
    background: var(--bg-panel); border: 1px solid var(--border); border-radius: 10px; margin-bottom: 10px;
}
.wl-chart-ticker {
    font-family: 'IBM Plex Mono', monospace; font-size: 20px; font-weight: 800;
    color: var(--txt-1); letter-spacing: -0.02em;
}
.wl-chart-label {
    font-family: 'IBM Plex Mono', monospace; font-size: 9px; color: var(--txt-muted);
    text-transform: uppercase; letter-spacing: .1em;
}

div[data-testid="stDataFrame"] { border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)

# Variabili foreground tema-dipendenti (contrasto badge/origini in chiaro e scuro)
st.markdown(f"""
<style>
:root {{
  --fg-l1: {TH['pills']['amber'][1]};
  --fg-l2: {TH['pills']['green'][1]};
  --fg-l3: {TH['pills']['red'][1]};
  --fg-v: {TH['pills']['cyan'][1]};
  --fg-p: {TH['pills']['violet'][1]};
  --fg-empty: {TH['muted']};
  --fg-origin-man: {TH['txt3']};
}}
</style>
""", unsafe_allow_html=True)

render_navbar("watchlist", hide_sidebar=True)
section_header("Portafoglio monitorato", "Watchlist & Livelli")


# ================================================================
# CLIENT GROQ — AUTONOMO (chiave SOLO da secrets, nessun valore nel codice)
# ================================================================
@st.cache_resource
def get_client():
    try:
        from groq import Groq
    except Exception:
        return None
    # Legge GROQ_API_KEY; se assente prova il vecchio nome secret (entrambi da Streamlit secrets)
    api_key = st.secrets.get("GROQ_API_KEY") or st.secrets.get("GROQ_KEY_FALLBACK")
    if not api_key:
        return None
    return Groq(api_key=api_key)

client = get_client()


PROMPT_VISION = """Sei un analista tecnico quantitativo. Analizza questo screenshot di un grafico finanziario.

Estrai in formato JSON puro (senza markdown, senza backtick, senza testo esterno):
{
  "ticker": "string — simbolo dello strumento (es. AAPL, CPR.MI, GOLD)",
  "livello_1": number,
  "livello_2": number,
  "livello_3": number,
  "vwap_1": number,
  "vwap_2": number,
  "vwap_3": number
}

Regole:
- "ticker": usa il simbolo esatto come appare sul grafico. Se non visibile, stringa vuota.
- "livello_1/2/3": i 3 livelli di prezzo orizzontali più rilevanti (supporti/resistenze evidenti). 0 se non ne trovi 3.
- "vwap_1/2/3": fino a 3 valori VWAP se etichettati o chiaramente leggibili. 0 se non visibili.
- Tutti i prezzi in formato numerico (non stringhe).
- Rispondi SOLO con l'oggetto JSON, nessun altro testo prima o dopo."""


def analizza_immagine(image_bytes: bytes, mime_type: str) -> dict:
    if client is None:
        raise RuntimeError("Client Groq non disponibile: aggiungi groq>=0.11.0 a requirements.txt e la chiave GROQ_API_KEY nei secrets.")
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{mime_type};base64,{b64}"

    messaggi = [
        {"role": "system", "content": "Rispondi SOLO con JSON valido, senza testo esterno né blocchi markdown."},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT_VISION},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        },
    ]
    modelli = ["qwen/qwen3.6-27b"]
    response = None
    ultimo_err = None
    for model in modelli:
        for effort in ("none", None):
            try:
                kwargs = {
                    "model": model,
                    "messages": messaggi,
                    "temperature": 0.1,
                    "max_completion_tokens": 1024,
                }
                if effort is not None:
                    kwargs["reasoning_effort"] = effort
                response = client.chat.completions.create(**kwargs)
                break
            except Exception as e:
                ultimo_err = e
                response = None
        if response is not None:
            break
    if response is None:
        raise RuntimeError(f"Groq ha fallito su tutti i modelli vision: {ultimo_err}")

    text = response.choices[0].message.content or ""
    text = re.sub(r".*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    if "{" in text and "}" in text:
        text = text[text.find("{"): text.rfind("}") + 1]

    if not text.strip():
        raise ValueError("Risposta vuota dal modello vision.")

    try:
        dati = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON non parsabile dal modello: {e}. Risposta grezza: {text[:200]}")

    defaults = {"ticker": "", "livello_1": 0, "livello_2": 0, "livello_3": 0,
                "vwap_1": 0, "vwap_2": 0, "vwap_3": 0}
    for k, v in defaults.items():
        if k not in dati or dati[k] is None:
            dati[k] = v
    return dati


COLONNE_ATTESE = [
    "Ticker",
    "Livello 1", "Nota 1", "Livello 2", "Nota 2", "Livello 3", "Nota 3",
    "VWAP 1", "Nota VWAP 1", "VWAP 2", "Nota VWAP 2", "VWAP 3", "Nota VWAP 3",
    "Screenshot", "Origine",
    "POC 1", "POC 1 Low", "POC 1 High", "Nota POC 1",
    "POC 2", "POC 2 Low", "POC 2 High", "Nota POC 2",
    "POC 3", "POC 3 Low", "POC 3 High", "Nota POC 3",
    "Auto_Indice",
]

GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN")
GITHUB_REPO = st.secrets.get("GITHUB_REPO")
CSV_PATH = "watchlist.csv"
STATE_PATH = "alert_state.json"
HISTORY_PATH = "alert_history.csv"
PREZZI_PATH = "prezzi_attuali.json"

COLONNE_NUMERICHE = [
    "Livello 1", "Livello 2", "Livello 3", "VWAP 1", "VWAP 2", "VWAP 3",
    "POC 1", "POC 1 Low", "POC 1 High", "POC 2", "POC 2 Low", "POC 2 High",
    "POC 3", "POC 3 Low", "POC 3 High",
]

_TEXT_COLS = {"Screenshot", "Origine", "Auto_Indice"}

def _is_text_col(col: str) -> bool:
    return col.startswith("Nota") or col in _TEXT_COLS

def _read_watchlist_github() -> pd.DataFrame | None:
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return None
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{CSV_PATH}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code != 200:
            return None
        contenuto = base64.b64decode(r.json()["content"]).decode()
        return pd.read_csv(io.StringIO(contenuto))
    except Exception as e:
        print(f"Errore lettura watchlist da GitHub: {e}")
        return None

def carica_watchlist() -> pd.DataFrame:
    df = _read_watchlist_github()
    if df is None or df.empty:
        if os.path.exists(CSV_PATH):
            try:
                df = pd.read_csv(CSV_PATH)
            except Exception:
                df = pd.DataFrame(columns=COLONNE_ATTESE)
        else:
            df = pd.DataFrame(columns=COLONNE_ATTESE)
    if df.empty:
        df = pd.DataFrame(columns=COLONNE_ATTESE)
    df = df.rename(columns=ALIAS_COLONNE)
    for col in COLONNE_ATTESE:
        if col not in df.columns:
            df[col] = "" if _is_text_col(col) else 0
    df = df[COLONNE_ATTESE]
    for col in COLONNE_ATTESE:
        if _is_text_col(col):
            df[col] = df[col].fillna("").astype(str).replace("nan", "")
    df["Origine"] = df["Origine"].replace("", "manuale")
    for col in _COLONNE_NUMERICHE:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0).astype(float)
# Migrazione zone: POC punto senza Low/High -> zona derivata (valore POC intatto)
    for k in (1, 2, 3):
        mask = (df[f"POC {k}"] != 0) & ((df[f"POC {k} Low"] == 0) | (df[f"POC {k} High"] == 0))
        if mask.any():
            lo, hi = zip(*[zona_poc_effettiva(p, 0, 0) for p in df.loc[mask, f"POC {k}"]])
            df.loc[mask, f"POC {k} Low"] = lo
            df.loc[mask, f"POC {k} High"] = hi
    # Auto-rimozione tickers sopra 25% di ritracciamento dal massimo storico
    # Se il prezzo si è ripreso di più del 25% dal massimo, rimuovi dalla watchlist
    if "Ticker" in df.columns and not df.empty:
        tickers_to_remove = []
        for _, row in df.iterrows():
            ticker = str(row["Ticker"]).strip().upper()
            # Usa la funzione mappa già definita nell'app
            ticker_td = mappa_ticker_twelvedata(ticker)
            try:
                url = f"https://api.twelvedata.com/time_series?symbol={ticker_td}&interval=1day&outputsize=250&apikey={TD_API_KEY}&order=ASC"
                r = requests.get(url, timeout=10)
                if r.status_code == 200:
                    dati = r.json()
                    if dati.get("values"):
                        closes = [float(v["close"]) for v in dati["values"]]
                        ath = max(closes)
                        prezzo_corrente = closes[-1]
                        dd_pct = (prezzo_corrente - ath) / ath * 100
                        # Se il prezzo si è ripreso di più del 25% dal massimo (drawdown > -25%)
                        # significa che il titolo non è più in "sconto" profondo
                        if dd_pct > -25:
                            tickers_to_remove.append(ticker)
            except Exception:
                pass  # Se fallisce il fetch, non rimuovere (conservativo)
        if tickers_to_remove:
            df = df[~df["Ticker"].isin(tickers_to_remove)]
            if not df.empty:
                commit_csv_su_github(df)
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated()]
    return df

def rinomina_ticker(vecchio_ticker: str, nuovo_ticker: str):
    df = carica_watchlist()
    vecchio_ticker = vecchio_ticker.strip().upper()
    nuovo_ticker = nuovo_ticker.strip().upper()
    if not nuovo_ticker or vecchio_ticker == nuovo_ticker:
        return df
    idx = df[df["Ticker"].str.upper() == vecchio_ticker].index
    if len(idx) == 0:
        return df
    df.at[idx[0], "Ticker"] = nuovo_ticker
    df.to_csv(CSV_PATH, index=False)
    commit_csv_su_github(df)
    return df

def salva_riga(ticker: str, l1, l2, l3, v1, v2, v3, n1="", n2="", n3="", nv1="", nv2="", nv3="", screenshot_path=None):
    df = carica_watchlist()
    ticker = ticker.strip().upper()
    if ticker in df["Ticker"].str.upper().values:
        idx = df[df["Ticker"].str.upper() == ticker].index[0]
        for col in ["Nota 1", "Nota 2", "Nota 3", "Nota VWAP 1", "Nota VWAP 2", "Nota VWAP 3", "Screenshot", "Origine"]:
            df[col] = df[col].astype(object)
        df.at[idx, "Livello 1"] = l1; df.at[idx, "Nota 1"] = n1
        df.at[idx, "Livello 2"] = l2; df.at[idx, "Nota 2"] = n2
        df.at[idx, "Livello 3"] = l3; df.at[idx, "Nota 3"] = n3
        df.at[idx, "VWAP 1"] = v1; df.at[idx, "Nota VWAP 1"] = nv1
        df.at[idx, "VWAP 2"] = v2; df.at[idx, "Nota VWAP 2"] = nv2
        df.at[idx, "VWAP 3"] = v3; df.at[idx, "Nota VWAP 3"] = nv3
        df.at[idx, "Origine"] = "manuale"
        if screenshot_path:
            df.at[idx, "Screenshot"] = screenshot_path
    else:
        nuova_riga = pd.DataFrame([{
            "Ticker": ticker,
            "Livello 1": l1, "Nota 1": n1, "Livello 2": l2, "Nota 2": n2, "Livello 3": l3, "Nota 3": n3,
            "VWAP 1": v1, "Nota VWAP 1": nv1, "VWAP 2": v2, "Nota VWAP 2": nv2, "VWAP 3": v3, "Nota VWAP 3": nv3,
            "Screenshot": screenshot_path or "", "Origine": "manuale",
            "POC 1": 0, "POC 1 Low": 0, "POC 1 High": 0, "Nota POC 1": "",
            "POC 2": 0, "POC 2 Low": 0, "POC 2 High": 0, "Nota POC 2": "",
            "POC 3": 0, "POC 3 Low": 0, "POC 3 High": 0, "Nota POC 3": "",
            "Auto_Indice": "",
        }])
        df = pd.concat([df, nuova_riga], ignore_index=True)
    df.to_csv(CSV_PATH, index=False)
    commit_csv_su_github(df)
    return df


# ================================================================
# HEADER + SEZIONE UPLOAD / ANALISI
# ================================================================
st.markdown(
    '<div class="wl-card">'
    '<div class="wl-card-head">🤖 Automazione watchlist</div>'
    '<div style="font-size:12.5px;line-height:1.55;color:var(--txt-2)">'
    'I titoli dello <b>screener</b> che toccano un POC o un VWAP entrano <b>da soli</b> nella watchlist '
    'con origine <span class="wl-origin auto">🤖 AUTO</span> e vengono rimossi quando escono dalla zona. '
    'I titoli che inserisci o modifichi a mano qui hanno origine <span class="wl-origin man">👤 MAN</span> '
    'e <b>non vengono mai toccati</b> dall\'automazione.'
    '</div></div>',
    unsafe_allow_html=True,
)

col_upload, col_result = st.columns([1, 1], gap="large")

with col_upload:
    st.markdown('<div class="wl-card-head">📸 Upload screenshot</div>', unsafe_allow_html=True)
    uploaded_file = st.file_uploader(
        "Carica screenshot del grafico (TradingView, broker, ecc.)",
        type=["png", "jpg", "jpeg", "webp"],
        label_visibility="collapsed",
    )
    # ⚠️ Upload screenshot disabilitato temporaneamente -
    # l'analisi immagini richiede configurazione GROQ API
    st.caption("📸 Analisi immagini disabilitata - configurare GROQ_API_KEY per riattivare")
    # Non mostrare upload file né pulsante analisi
    # [L'analisi immagini è disabilitata - vedere sopra]

with col_result:
    if "ultima_analisi" in st.session_state:
        dati = st.session_state["ultima_analisi"]
        st.markdown('<div class="wl-card-head">🧩 Dati estratti (verifica e salva)</div>', unsafe_allow_html=True)

        st.markdown(
            '<div class="wl-ai-box"><b>🧠 Lettura AI</b> — il modello ha interpretato lo screenshot. '
            'Verifica ogni valore prima di salvare: la lettura può contenere errori, soprattutto su '
            'VWAP non etichettati o livelli secondari.</div>',
            unsafe_allow_html=True,
        )

        ticker_edit = st.text_input("Ticker", value=dati.get("ticker", ""))
        col_l, col_v = st.columns(2)
        with col_l:
            st.markdown("**Livelli**")
            l1_edit = st.number_input("Livello 1", value=float(dati.get("livello_1", 0) or 0))
            l2_edit = st.number_input("Livello 2", value=float(dati.get("livello_2", 0) or 0))
            l3_edit = st.number_input("Livello 3", value=float(dati.get("livello_3", 0) or 0))
        with col_v:
            st.markdown("**VWAP**")
            v1_edit = st.number_input("VWAP 1", value=float(dati.get("vwap_1", 0) or 0))
            v2_edit = st.number_input("VWAP 2", value=float(dati.get("vwap_2", 0) or 0))
            v3_edit = st.number_input("VWAP 3", value=float(dati.get("vwap_3", 0) or 0))
        n1_edit = st.text_input("Nota Livello 1", value="", placeholder="es. supporto storico")
        n2_edit = st.text_input("Nota Livello 2", value="", placeholder="es. media mobile 200")
        n3_edit = st.text_input("Nota Livello 3", value="", placeholder="es. resistenza ATH")
        nv1_edit = st.text_input("Nota VWAP 1", value="")
        nv2_edit = st.text_input("Nota VWAP 2", value="")
        nv3_edit = st.text_input("Nota VWAP 3", value="")

        c_save, c_reset = st.columns([3, 1])
        with c_save:
            if st.button("💾 Salva in watchlist", type="primary", use_container_width=True):
                screenshot_path = None
                #if uploaded_file is not None:
                    #estensione = (uploaded_file.type or "image/png").split("/")[-1]
                    #if estensione == "jpeg":
                        #estensione = "jpg"
                    #screenshot_path = carica_screenshot_su_github(
                        #ticker_edit.strip().upper() or "TICKER", uploaded_file.getvalue(), estensione
                    #)
                salva_riga(ticker_edit, l1_edit, l2_edit, l3_edit, v1_edit, v2_edit, v3_edit,
                           n1_edit, n2_edit, n3_edit, nv1_edit, nv2_edit, nv3_edit, screenshot_path)
                del st.session_state["ultima_analisi"]
                st.rerun()
        with c_reset:
            if st.button("🔄", use_container_width=True, help="Scarta e ricomincia"):
                del st.session_state["ultima_analisi"]
                st.rerun()
    else:
        st.markdown(
            '<div class="wl-card" style="min-height:200px;display:flex;align-items:center;justify-content:center;color:var(--txt-muted);text-align:center">'
            '<div><div style="font-size:36px;opacity:.5">📸</div>'
            '<div style="font-size:12px;margin-top:8px">Carica uno screenshot a sinistra<br>per estrarre ticker, livelli e VWAP</div>'
            '</div></div>',
            unsafe_allow_html=True,
        )


# ================================================================
# INSERIMENTO MANUALE
# ================================================================
with st.expander("➕ Inserimento Manuale Ticker", expanded=False):
    with st.form("form_inserimento_manuale"):
        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1:
            m_ticker = st.text_input("Ticker (es. AAPL, CPR.MI)").strip().upper()
            m_l1 = st.number_input("Livello 1", value=0.0)
            m_l2 = st.number_input("Livello 2", value=0.0)
            m_l3 = st.number_input("Livello 3", value=0.0)
        with col_m2:
            m_n1 = st.text_input("Nota L1")
            m_n2 = st.text_input("Nota L2")
            m_n3 = st.text_input("Nota L3")
        with col_m3:
            st.markdown("**VWAP**")
            m_v1 = st.number_input("VWAP 1", value=0.0)
            m_v2 = st.number_input("VWAP 2", value=0.0)
            m_v3 = st.number_input("VWAP 3", value=0.0)
            m_nv1 = st.text_input("Nota V1")
            m_nv2 = st.text_input("Nota V2")
            m_nv3 = st.text_input("Nota V3")
        m_submit = st.form_submit_button("💾 Salva Ticker Manuale", use_container_width=True)
    if m_submit:
        if not m_ticker:
            st.error("Il Ticker è obbligatorio.")
        else:
            df_check = carica_watchlist()
            if m_ticker in df_check["Ticker"].values:
                st.warning(f"Il ticker {m_ticker} esiste già. Modificalo direttamente dalla tabella.")
            else:
                salva_riga(m_ticker, m_l1, m_l2, m_l3, m_v1, m_v2, m_v3, m_n1, m_n2, m_n3, m_nv1, m_nv2, m_nv3)
                st.success(f"Ticker {m_ticker} aggiunto correttamente.")
                st.rerun()

st.divider()

# ================================================================
# WATCHLIST TABELLA
# ================================================================
st.markdown('<div class="wl-card-head">📋 Watchlist salvata</div>', unsafe_allow_html=True)
df = carica_watchlist()

TD_API_KEY = st.secrets.get("TWELVEDATA_API_KEY")
CRYPTO_NOTE = {"BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "BNB", "LTC"}
_ULTIME_CHIAMATE_API = []

def rispetta_rate_limit():
    ora = time.time()
    while _ULTIME_CHIAMATE_API and ora - _ULTIME_CHIAMATE_API[0] > 60:
        _ULTIME_CHIAMATE_API.pop(0)
    if len(_ULTIME_CHIAMATE_API) >= 7:
        attesa = 60 - (ora - _ULTIME_CHIAMATE_API[0]) + 1
        if attesa > 0:
            time.sleep(attesa)
        while _ULTIME_CHIAMATE_API and time.time() - _ULTIME_CHIAMATE_API[0] > 60:
            _ULTIME_CHIAMATE_API.pop(0)
    _ULTIME_CHIAMATE_API.append(time.time())

def mappa_ticker_twelvedata(ticker: str) -> str:
    t = ticker.strip().upper()
    for base in CRYPTO_NOTE:
        if t == f"{base}USD":
            return f"{base}/USD"
    if len(t) == 6 and t.isalpha() and t[:3] not in CRYPTO_NOTE:
        return f"{t[:3]}/{t[3:]}"
    return t

_ULTIMO_ERRORE_TD = None

@st.cache_data(ttl=1800)
def ottieni_time_series(simbolo: str, interval: str, outputsize: int) -> pd.DataFrame:
    global _ULTIMO_ERRORE_TD
    if not TD_API_KEY:
        return pd.DataFrame()
    try:
        rispetta_rate_limit()
        r = requests.get("https://api.twelvedata.com/time_series",
            params={"symbol": simbolo, "interval": interval, "outputsize": outputsize, "apikey": TD_API_KEY, "order": "ASC"})
        dati = r.json()
        if dati.get("status") == "error" or "values" not in dati:
            _ULTIMO_ERRORE_TD = dati.get("message", str(dati))
            print(f"Twelve Data errore per {simbolo}: {_ULTIMO_ERRORE_TD}")
            return pd.DataFrame()
        _ULTIMO_ERRORE_TD = None
        df = pd.DataFrame(dati["values"])
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.set_index("datetime").sort_index()
        for col in ("open", "high", "low", "close", "volume"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
        return df.dropna(subset=["Close"])
    except Exception as e:
        _ULTIMO_ERRORE_TD = str(e)
        print(f"Errore Twelve Data per {simbolo}: {e}")
        return pd.DataFrame()

def determina_exchange(simbolo: str) -> str:
    return "nasdaq"

@st.cache_data(ttl=300)
def carica_prezzi_condivisi():
    path = "prezzi_attuali.json"
    if GITHUB_TOKEN and GITHUB_REPO:
        try:
            r = requests.get(f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}", headers={"Authorization": f"token {GITHUB_TOKEN}"})
            if r.status_code == 200:
                contenuto = base64.b64decode(r.json()["content"]).decode()
                dati = json.loads(contenuto)
                return dati.get("prezzi", {}), dati.get("aggiornato_il", "")
        except Exception:
            pass
    if os.path.exists(path):
        with open(path) as f:
            dati = json.load(f)
            return dati.get("prezzi", {}), dati.get("aggiornato_il", "")
    return {}, ""

def elimina_riga(ticker: str):
    df = carica_watchlist()
    df = df[df["Ticker"] != ticker]
    df.to_csv(CSV_PATH, index=False)
    commit_csv_su_github(df)

if df.empty or "Ticker" not in df.columns:
    st.info("Nessun dato salvato ancora.")
else:
    ricerca = st.text_input("Cerca ticker", placeholder="🔍 Cerca ticker...", label_visibility="collapsed")
    df_visualizzata = df[df["Ticker"].str.contains(ricerca.strip(), case=False, na=False)] if ricerca else df
    if not df_visualizzata.empty:
        df_visualizzata = df_visualizzata.drop_duplicates(subset=["Ticker"], keep="last").reset_index(drop=True)

    COLS = [2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0.3, 0.3, 0.3, 0.3, 0.3]
    cols = st.columns(COLS)
    etichette = list(zip(cols[:11], ("Ticker", "L1", "L2", "L3", "V1", "V2", "V3", "POC1", "POC2", "POC3", "Prezzo")))
    for col, label in etichette:
        col.markdown(f'<div class="wl-header">{label}</div>', unsafe_allow_html=True)
    for col in cols[11:]:
        col.markdown('<div class="wl-header">&nbsp;</div>', unsafe_allow_html=True)

    if df_visualizzata.empty:
        st.caption("Nessun ticker corrisponde alla ricerca.")

    def badge(valore, classe, nota="", zona=None):
        if pd.isna(valore) or valore == 0:
            return f'<span class="wl-badge empty">—</span>'
        t = ""
        if zona and zona[0] > 0 and zona[1] > 0:
            t = f"zona {zona[0]:g}–{zona[1]:g}"
        combo = " · ".join(x for x in [nota, t] if x)
        title = f' title="{combo}"' if combo else ""
        icona = " 📝" if nota else ""
        return f'<span class="wl-badge {classe}"{title}>{valore:g}{icona}</span>'

    if "editing_ticker" not in st.session_state:
        st.session_state["editing_ticker"] = None

    prezzi_condivisi = st.session_state["prezzi_sessione"]
    prezzi_aggiornati_il = st.session_state["prezzi_aggiornati_il"]
    if prezzi_aggiornati_il:
        st.caption(f"💹 Prezzi aggiornati da ultimo controllo alert: {prezzi_aggiornati_il}")

    for _, r in df_visualizzata.iterrows():
        ticker_riga = r["Ticker"]
        origine_riga = str(r.get("Origine", "manuale")).strip().lower()

        # Zone POC effettive (auto = reali; manuale/punto = derivate)
        zone_poc = {}
        for k in (1, 2, 3):
            p = float(r.get(f"POC {k}", 0) or 0)
            if p != 0:
                zone_poc[k] = zona_poc_effettiva(p, r.get(f"POC {k} Low"), r.get(f"POC {k} High"))
            else:
                zone_poc[k] = (0.0, 0.0)

        if st.session_state["editing_ticker"] == ticker_riga:
            c = st.columns(COLS)
            nuovo_nome_ticker = c[0].text_input("Ticker", value=ticker_riga, key=f"edit_ticker_{ticker_riga}_{_}", label_visibility="collapsed")
            nl1 = c[1].number_input("L1", value=float(r["Livello 1"]), key=f"edit_l1_{ticker_riga}_{_}", label_visibility="collapsed")
            nl2 = c[2].number_input("L2", value=float(r["Livello 2"]), key=f"edit_l2_{ticker_riga}_{_}", label_visibility="collapsed")
            nl3 = c[3].number_input("L3", value=float(r["Livello 3"]), key=f"edit_l3_{ticker_riga}_{_}", label_visibility="collapsed")
            nv1 = c[4].number_input("V1", value=float(r["VWAP 1"]), key=f"edit_v1_{ticker_riga}_{_}", label_visibility="collapsed")
            nv2 = c[5].number_input("V2", value=float(r["VWAP 2"]), key=f"edit_v2_{ticker_riga}_{_}", label_visibility="collapsed")
            nv3 = c[6].number_input("V3", value=float(r["VWAP 3"]), key=f"edit_v3_{ticker_riga}_{_}", label_visibility="collapsed")
            c[7].markdown(badge(r["POC 1"], "p1", zona=zone_poc[1]), unsafe_allow_html=True)
            c[8].markdown(badge(r["POC 2"], "p2", zona=zone_poc[2]), unsafe_allow_html=True)
            c[9].markdown(badge(r["POC 3"], "p3", zona=zone_poc[3]), unsafe_allow_html=True)
            c[10].write("")
            if c[11].button("💾", key=f"save_{ticker_riga}_{_}"):
                nota_1 = st.session_state.get(f"edit_n1_{ticker_riga}_{_}", r["Nota 1"])
                nota_2 = st.session_state.get(f"edit_n2_{ticker_riga}_{_}", r["Nota 2"])
                nota_3 = st.session_state.get(f"edit_n3_{ticker_riga}_{_}", r["Nota 3"])
                nota_v1 = st.session_state.get(f"edit_nv1_{ticker_riga}_{_}", r["Nota VWAP 1"])
                nota_v2 = st.session_state.get(f"edit_nv2_{ticker_riga}_{_}", r["Nota VWAP 2"])
                nota_v3 = st.session_state.get(f"edit_nv3_{ticker_riga}_{_}", r["Nota VWAP 3"])
                ticker_finale = ticker_riga
                if nuovo_nome_ticker.strip().upper() != ticker_riga.strip().upper():
                    rinomina_ticker(ticker_riga, nuovo_nome_ticker)
                    ticker_finale = nuovo_nome_ticker.strip().upper()
                salva_riga(ticker_finale, nl1, nl2, nl3, nv1, nv2, nv3, nota_1, nota_2, nota_3, nota_v1, nota_v2, nota_v3)
                st.session_state["editing_ticker"] = None
                st.rerun()
            if c[12].button("✖", key=f"cancel_{ticker_riga}_{_}"):
                st.session_state["editing_ticker"] = None
                st.rerun()
            for cc in (c[13], c[14], c[15]):
                cc.write("")
            _, nc1, nc2, nc3, nc4, nc5, nc6, _ = st.columns([2, 1, 1, 1, 1, 1, 1, 2.7])
            nc1.text_input("Nota L1", value=str(r["Nota 1"] or ""), key=f"edit_n1_{ticker_riga}_{_}", label_visibility="collapsed")
            nc2.text_input("Nota L2", value=str(r["Nota 2"] or ""), key=f"edit_n2_{ticker_riga}_{_}", label_visibility="collapsed")
            nc3.text_input("Nota L3", value=str(r["Nota 3"] or ""), key=f"edit_n3_{ticker_riga}_{_}", label_visibility="collapsed")
            nc4.text_input("Nota V1", value=str(r["Nota VWAP 1"] or ""), key=f"edit_nv1_{ticker_riga}_{_}", label_visibility="collapsed")
            nc5.text_input("Nota V2", value=str(r["Nota VWAP 2"] or ""), key=f"edit_nv2_{ticker_riga}_{_}", label_visibility="collapsed")
            nc6.text_input("Nota V3", value=str(r["Nota VWAP 3"] or ""), key=f"edit_nv3_{ticker_riga}_{_}", label_visibility="collapsed")
        else:
            c = st.columns(COLS)
            prefisso_origine = "🤖 " if origine_riga == "auto" else ""
            if c[0].button(prefisso_origine + ticker_riga, key=f"select_{ticker_riga}_{_}", use_container_width=True):
                st.session_state["ticker_grafico"] = ticker_riga
                st.rerun()
            c[1].markdown(badge(r["Livello 1"], "l1", r["Nota 1"]), unsafe_allow_html=True)
            c[2].markdown(badge(r["Livello 2"], "l2", r["Nota 2"]), unsafe_allow_html=True)
            c[3].markdown(badge(r["Livello 3"], "l3", r["Nota 3"]), unsafe_allow_html=True)
            c[4].markdown(badge(r["VWAP 1"], "v1", r["Nota VWAP 1"]), unsafe_allow_html=True)
            c[5].markdown(badge(r["VWAP 2"], "v2", r["Nota VWAP 2"]), unsafe_allow_html=True)
            c[6].markdown(badge(r["VWAP 3"], "v3", r["Nota VWAP 3"]), unsafe_allow_html=True)
            c[7].markdown(badge(r["POC 1"], "p1", r["Nota POC 1"], zona=zone_poc[1]), unsafe_allow_html=True)
            c[8].markdown(badge(r["POC 2"], "p2", r["Nota POC 2"], zona=zone_poc[2]), unsafe_allow_html=True)
            c[9].markdown(badge(r["POC 3"], "p3", r["Nota POC 3"], zona=zone_poc[3]), unsafe_allow_html=True)

            prezzo_riga = prezzi_condivisi.get(ticker_riga)
            if prezzo_riga is not None:
                c[10].markdown(f'<span class="wl-price">{prezzo_riga:.2f}</span>', unsafe_allow_html=True)
            else:
                c[10].markdown('<span style="color:var(--txt-muted);">—</span>', unsafe_allow_html=True)

            ticker_td_riga = mappa_ticker_twelvedata(ticker_riga)
            tv_symbol = ticker_td_riga.replace('/', '')
            tv_url = f"https://www.tradingview.com/symbols/{tv_symbol}/"
            exch = determina_exchange(ticker_td_riga)
            fc_url = f"https://terminal.forecaster.biz/instrument/{exch}/{ticker_riga.lower()}/overview"
            c[11].markdown(f'<a href="{tv_url}" target="_blank" style="text-decoration:none;">📈</a>', unsafe_allow_html=True)
            c[12].markdown(f'<a href="{fc_url}" target="_blank" style="text-decoration:none;">🔮</a>', unsafe_allow_html=True)
            if r.get("Screenshot"):
                if c[13].button("🖼️", key=f"screenshot_{ticker_riga}_{_}"):
                    st.session_state["screenshot_da_mostrare"] = r["Screenshot"]
                    st.rerun()
            else:
                c[13].write("")
            if c[14].button("✏️", key=f"edit_{ticker_riga}_{_}"):
                st.session_state["editing_ticker"] = ticker_riga
                st.rerun()
            if c[15].button("🗑️", key=f"del_{ticker_riga}_{_}"):
                elimina_riga(ticker_riga)
                st.rerun()

    st.write("")

    if st.session_state.get("screenshot_da_mostrare"):
        path = st.session_state["screenshot_da_mostrare"]
        try:
            r_img = requests.get(f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}", headers={"Authorization": f"token {GITHUB_TOKEN}"})
            if r_img.status_code == 200:
                img_bytes = base64.b64decode(r_img.json()["content"])
                with st.expander("🖼️ Screenshot originale", expanded=True):
                    st.image(img_bytes, use_container_width=True)
                    if st.button("Chiudi anteprima"):
                        st.session_state["screenshot_da_mostrare"] = None
                        st.rerun()
            else:
                st.warning("Screenshot non trovato nel repo.")
        except Exception as e:
            st.warning(f"Impossibile caricare lo screenshot: {e}")

    dim_kb = dimensione_repo_kb()
    if dim_kb is not None:
        dim_mb = dim_kb / 1024
        soglia_mb = 800
        if dim_mb >= soglia_mb:
            st.warning(f"⚠️ Il repo occupa {dim_mb:.0f} MB, si sta avvicinando al limite consigliato (~1 GB). Valuta di ripulire vecchi screenshot.")
        else:
            st.caption(f"💾 Spazio repo: {dim_mb:.0f} MB / ~1000 MB")

    # ================================================================
    # GRAFICO TICKER SELEZIONATO (colori tema-aware + bande zona POC)
    # ================================================================
    if "ticker_grafico" not in st.session_state or st.session_state["ticker_grafico"] not in df["Ticker"].values:
        st.session_state["ticker_grafico"] = df["Ticker"].iloc[0]
    ticker_selezionato = st.session_state["ticker_grafico"]
    riga = df[df["Ticker"] == ticker_selezionato].iloc[0]
    livelli = [float(riga[f"Livello {i}"]) for i in (1, 2, 3) if pd.notna(riga[f"Livello {i}"]) and riga[f"Livello {i}"] != 0]
    vwap = [float(riga[f"VWAP {i}"]) for i in (1, 2, 3) if pd.notna(riga[f"VWAP {i}"]) and riga[f"VWAP {i}"] != 0]

    import json as _json

    TIMEFRAMES = {"4H": ("4h", 300), "1D": ("1day", 500), "1W": ("1week", 260), "1M": ("1month", 120)}

    origine_selezionato = str(riga.get("Origine", "manuale")).strip().lower()
    origine_pill = '<span class="wl-origin auto">🤖 AUTO</span>' if origine_selezionato == "auto" else '<span class="wl-origin man">👤 MAN</span>'
    st.markdown(
        f'<div class="wl-chart-head">'
        f'<div><div class="wl-chart-label">Grafico attivo</div>'
        f'<div class="wl-chart-ticker">{ticker_selezionato} {origine_pill}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    timeframe = st.radio("Timeframe", list(TIMEFRAMES.keys()), index=1, horizontal=True, label_visibility="collapsed")
    intervallo, outputsize = TIMEFRAMES[timeframe]

    ticker_td = mappa_ticker_twelvedata(ticker_selezionato)
    storico = ottieni_time_series(ticker_td, intervallo, outputsize)
    if storico.empty:
        mappa_yf_periodo = {"4h": "2y", "1day": "10y", "1week": "10y", "1month": "max"}
        storico = storico_yfinance(ticker_selezionato, mappa_yf_periodo.get(intervallo, "1y"), intervallo.replace("1day", "1d").replace("1week", "1wk").replace("1month", "1mo").replace("4h", "60m"))

    if storico.empty:
        dettaglio = f" — {_ULTIMO_ERRORE_TD}" if _ULTIMO_ERRORE_TD else ""
        st.warning(f"Nessun dato storico trovato per {ticker_selezionato} ({ticker_td}){dettaglio}.")
    else:
        usa_timestamp = timeframe == "4H"
        candele = [
            {"time": int(idx.timestamp()) if usa_timestamp else idx.strftime("%Y-%m-%d"),
             "open": round(r["Open"], 4), "high": round(r["High"], 4), "low": round(r["Low"], 4), "close": round(r["Close"], 4)}
            for idx, r in storico.iterrows()
        ]
        # Colori linee tema-aware
        c_l1, c_l2, c_l3 = TH["chart"]["poc_mid"], TH["chart"]["up"], TH["chart"]["down"]
        c_vw = TH["accent"]
        c_poc = TH["pills"]["violet"][1]
        c_up, c_down = TH["chart"]["up"], TH["chart"]["down"]
        linee_livelli_js = "\n".join(
            f'candleSeries.createPriceLine({{price: {liv}, color: "{[c_l1, c_l2, c_l3][i % 3]}", lineWidth: 2, lineStyle: 0, title: "L{i+1}: {liv}"}});'
            for i, liv in enumerate(livelli))
        linee_vwap_js = "\n".join(
            f'candleSeries.createPriceLine({{price: {v}, color: "{c_vw}", lineWidth: 2, lineStyle: 2, title: "V{i+1}: {v}"}});'
            for i, v in enumerate(vwap))
        # POC come zone: linea centrale tratteggiata + bordi dotted della banda
        parti_poc = []
        for k in (1, 2, 3):
            p = float(riga[f"POC {k}"]) if pd.notna(riga[f"POC {k}"]) else 0.0
            if p != 0:
                lo, hi = zona_poc_effettiva(p, riga[f"POC {k} Low"], riga[f"POC {k} High"])
                parti_poc.append(
                    f'candleSeries.createPriceLine({{price: {p}, color: "{c_poc}", lineWidth: 2, lineStyle: 2, title: "POC{k}: {p:g} [{lo:g}–{hi:g}]"}});'
                )
                if hi > lo:
                    parti_poc.append(
                        f'candleSeries.createPriceLine({{price: {lo}, color: "{c_poc}", lineWidth: 1, lineStyle: 1, title: ""}});'
                    )
                    parti_poc.append(
                        f'candleSeries.createPriceLine({{price: {hi}, color: "{c_poc}", lineWidth: 1, lineStyle: 1, title: ""}});'
                    )
        linee_poc_js = "\n".join(parti_poc)

        chart_html = f"""
        <div id="chart_container" style="width:100%; height:600px; border:1px solid {TH['border']}; border-radius:10px; overflow:hidden;"></div>
        <script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
        <script>
          const container = document.getElementById('chart_container');
          const chart = LightweightCharts.createChart(container, {{
            width: container.clientWidth, height: 600,
            layout: {{
              background: {{ type: 'solid', color: '{TH['bg_panel']}' }},
              textColor: '{TH['txt2']}',
              fontFamily: "'IBM Plex Mono', monospace",
              fontSize: 11,
            }},
            grid: {{ vertLines: {{ color: '{TH['chart']['grid']}' }}, horzLines: {{ color: '{TH['chart']['grid']}' }} }},
            timeScale: {{ borderColor: '{TH['border_strong']}', timeVisible: {str(usa_timestamp).lower()} }},
            rightPriceScale: {{ borderColor: '{TH['border_strong']}' }},
            crosshair: {{
              mode: 1,
              vertLine: {{ color: '{TH['accent']}', width: 1, style: 2 }},
              horzLine: {{ color: '{TH['accent']}', width: 1, style: 2 }},
            }},
          }});
          const candleSeries = chart.addCandlestickSeries({{
            upColor: '{c_up}', downColor: '{c_down}',
            borderVisible: false,
            wickUpColor: '{c_up}', wickDownColor: '{c_down}',
          }});
          candleSeries.setData({_json.dumps(candele)});
          {linee_livelli_js}
          {linee_vwap_js}
          {linee_poc_js}
          chart.timeScale().fitContent();
          new ResizeObserver(entries => {{ chart.applyOptions({{ width: entries[0].contentRect.width }}); }}).observe(container);
        </script>
        """
        st.components.v1.html(chart_html, height=620)

st.divider()
st.markdown('<div class="wl-card-head">🕘 Storico Alert</div>', unsafe_allow_html=True)
HISTORY_PATH = "alert_history.csv"

@st.cache_data(ttl=60)
def carica_storico_alert() -> pd.DataFrame:
    colonne = ["Data", "Ticker", "Livelli Toccati", "Convergenza", "Regime", "Prezzo al momento"]
    if GITHUB_TOKEN and GITHUB_REPO:
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{HISTORY_PATH}"
            headers = {"Authorization": f"token {GITHUB_TOKEN}"}
            r = requests.get(url, headers=headers)
            if r.status_code == 200:
                contenuto = base64.b64decode(r.json()["content"]).decode()
                return pd.read_csv(io.StringIO(contenuto))
        except Exception:
            pass
    if os.path.exists(HISTORY_PATH):
        return pd.read_csv(HISTORY_PATH)
    return pd.DataFrame(columns=colonne)

storico_alert = carica_storico_alert()
if storico_alert.empty:
    st.caption("Nessun alert ancora scattato.")
else:
    st.dataframe(storico_alert.sort_values("Data", ascending=False), use_container_width=True, hide_index=True)