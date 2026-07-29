import streamlit as st
import pandas as pd
import os
import io
import datetime
import time
import json
import requests
import yfinance as yf
from PIL import Image
from google import genai
from google.genai import types
import base64

MAPPA_BORSA_EUROPEA = {
    "CPR": "CPR.MI",    # Campari, Borsa Italiana
    "RI": "RI.PA",      # Pernod Ricard, Euronext Paris
    "NESN": "NESN.SW",  # Nestlé, SIX Swiss Exchange
    "AF": "AF.PA",      # Air France-KLM, Euronext Paris
}

def storico_yfinance(ticker: str, period: str, interval: str) -> pd.DataFrame:
    """Fallback su yfinance. auto_adjust=True rettifica dividendi e split."""
    simbolo = MAPPA_BORSA_EUROPEA.get(ticker, ticker)
    try:
        h = yf.Ticker(simbolo).history(period=period, interval=interval, auto_adjust=True)
        return h.dropna(subset=["Close"]) if not h.empty else pd.DataFrame()
    except Exception as e:
        print(f"Errore storico yfinance per {simbolo}: {e}")
        return pd.DataFrame()

CSV_PATH = "watchlist.csv"
MODEL_NAME = "gemini-2.5-flash"

st.set_page_config(page_title="Watchlist Grafici", layout="wide", page_icon="📈")

# ---------------------------------------------------------------
# STILE
# ---------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=IBM+Plex+Mono:wght@400;600&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.block-container { padding-top: 2rem; padding-bottom: 2rem; padding-left: 2rem; padding-right: 2rem; max-width: 100%; }

h1 { font-size: 1.6rem !important; font-weight: 700 !important; letter-spacing: -0.02em; margin-bottom: 0.2rem !important; }
h3 { font-size: 1.05rem !important; font-weight: 600 !important; color: #9aa4b2 !important;
     text-transform: uppercase; letter-spacing: 0.06em; margin-top: 0 !important; }

hr { margin: 1.4rem 0 !important; border-color: #232733 !important; }

div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
    display: flex; align-items: center;
}

.wl-badge {
    font-family: 'IBM Plex Mono', monospace; font-size: 0.82rem; font-weight: 600;
    padding: 3px 10px; border-radius: 6px; display: inline-block;
    border: 1px solid transparent;
}
.wl-badge.l1 { color: #f0b90b; background: rgba(240,185,11,0.10); border-color: rgba(240,185,11,0.25); }
.wl-badge.l2 { color: #00c176; background: rgba(0,193,118,0.10); border-color: rgba(0,193,118,0.25); }
.wl-badge.l3 { color: #ff4d4d; background: rgba(255,77,77,0.10); border-color: rgba(255,77,77,0.25); }
.wl-badge.v1 { color: #00b4d8; background: rgba(0,180,216,0.10); border-color: rgba(0,180,216,0.25); }
.wl-badge.v2 { color: #00b4d8; background: rgba(0,180,216,0.10); border-color: rgba(0,180,216,0.25); }
.wl-badge.v3 { color: #00b4d8; background: rgba(0,180,216,0.10); border-color: rgba(0,180,216,0.25); }
.wl-badge.empty { color: #4a5568; background: transparent; border: 1px dashed #2d3340; }

.wl-header {
    font-family: 'Inter', sans-serif; font-size: 0.72rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.08em; color: #6b7280;
    padding-bottom: 6px; border-bottom: 1px solid #232733; margin-bottom: 4px;
}

div[data-testid="stButton"] button {
    border: 1px solid #2d3340; background: transparent; color: #6b7280;
    border-radius: 6px; transition: all 0.15s ease;
}
div[data-testid="column"]:nth-of-type(1) div[data-testid="stButton"] button {
    color: #e8eaed; font-family: 'IBM Plex Mono', monospace; font-weight: 600;
    text-align: left; border: none; background: transparent; padding-left: 0;
}
div[data-testid="column"]:nth-of-type(1) div[data-testid="stButton"] button:hover {
    color: #f0b90b; background: transparent; border: none;
}
div[data-testid="stButton"] button:hover {
    border-color: #ff4d4d; color: #ff4d4d; background: rgba(255,77,77,0.08);
}

div[data-testid="stFileUploaderDropzone"] {
    border: 1px dashed #2d3340; background: #0f1219; border-radius: 10px;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------
# CLIENT GEMINI
# ---------------------------------------------------------------
@st.cache_resource
def get_client():
    api_key = st.secrets["GEMINI_API_KEY"]
    return genai.Client(api_key=api_key)

client = get_client()

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "ticker": {"type": "STRING"},
        "livello_1": {"type": "NUMBER"},
        "livello_2": {"type": "NUMBER"},
        "livello_3": {"type": "NUMBER"},
        "vwap_1": {"type": "NUMBER"},
        "vwap_2": {"type": "NUMBER"},
        "vwap_3": {"type": "NUMBER"},
    },
    "required": ["ticker"],
}

PROMPT = """Analizza questo screenshot di un grafico finanziario (piattaforma di trading).
Estrai:
1. Il ticker/simbolo dello strumento.
2. Fino a 3 livelli di prezzo numerici rilevanti (supporti, resistenze, linee orizzontali).
3. Fino a 3 valori VWAP (Volume Weighted Average Price) se visibili sul grafico.
Se non trovi un dato, lascialo a 0. Rispondi SOLO con i dati richiesti in JSON."""

def analizza_immagine(image_bytes: bytes, mime_type: str) -> dict:
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            PROMPT,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
            safety_settings=[
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
            ],
        ),
    )

    if not response.candidates:
        raise ValueError(f"Nessuna risposta da Gemini. Prompt feedback: {response.prompt_feedback}")

    candidate = response.candidates[0]
    if candidate.finish_reason not in ("STOP", 1):
        raise ValueError(f"Risposta bloccata. finish_reason={candidate.finish_reason}")

    return json.loads(response.text)

# ---------------------------------------------------------------
# CSV: lettura / scrittura
# ---------------------------------------------------------------
# Schema ALLINEATO a watchlist_io.py (single source of truth concettuale):
# aggiungo Origine (manuale|auto), POC e Nota POC. Così app.py non taglierà mai
# più queste colonne quando riscrive il CSV, e l'automazione di Screening può usarle.
COLONNE_ATTESE = [
    "Ticker",
    "Livello 1", "Nota 1", "Livello 2", "Nota 2", "Livello 3", "Nota 3",
    "VWAP 1", "Nota VWAP 1", "VWAP 2", "Nota VWAP 2", "VWAP 3", "Nota VWAP 3",
    "Screenshot",
    "Origine",
    "POC",
    "Nota POC",
]

GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN")
GITHUB_REPO = st.secrets.get("GITHUB_REPO")

def commit_csv_su_github(df: pd.DataFrame):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{CSV_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    r = requests.get(url, headers=headers)
    sha = r.json().get("sha") if r.status_code == 200 else None

    contenuto_b64 = base64.b64encode(df.to_csv(index=False).encode()).decode()
    payload = {
        "message": "Aggiorna watchlist.csv da app Streamlit",
        "content": contenuto_b64,
        "branch": "main",
    }
    if sha:
        payload["sha"] = sha

    resp = requests.put(url, headers=headers, json=payload)
    if resp.status_code not in (200, 201):
        st.warning(f"Salvataggio su GitHub fallito: {resp.status_code} {resp.text[:200]}")

def carica_screenshot_su_github(ticker: str, contenuto_bytes: bytes, estensione: str) -> str | None:
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return None

    nome_file = f"screenshots/{ticker}_{int(time.time())}.{estensione}"
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{nome_file}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    payload = {
        "message": f"Aggiungi screenshot {ticker}",
        "content": base64.b64encode(contenuto_bytes).decode(),
        "branch": "main",
    }
    resp = requests.put(url, headers=headers, json=payload)
    if resp.status_code in (200, 201):
        return nome_file
    st.warning(f"Salvataggio screenshot fallito: {resp.status_code} {resp.text[:200]}")
    return None

@st.cache_data(ttl=600)
def dimensione_repo_kb() -> int | None:
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return None
    try:
        r = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}",
            headers={"Authorization": f"token {GITHUB_TOKEN}"},
        )
        if r.status_code == 200:
            return r.json().get("size")
    except Exception:
        pass
    return None

ALIAS_COLONNE = {
    "ticker": "Ticker",
    "livello": "Livello 1",
    "livello_1": "Livello 1", "livello_2": "Livello 2", "livello_3": "Livello 3",
    "vwap_1": "VWAP 1", "vwap_2": "VWAP 2", "vwap_3": "VWAP 3",
    "origine": "Origine",
    "poc": "POC",
}

def _read_watchlist_github() -> pd.DataFrame | None:
    """Legge watchlist.csv dal repo GitHub (fonte di verità persistente)."""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return None
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{CSV_PATH}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            return None
        contenuto = base64.b64decode(r.json()["content"]).decode()
        return pd.read_csv(io.StringIO(contenuto))
    except Exception as e:
        print(f"Errore lettura watchlist da GitHub: {e}")
        return None

def carica_watchlist() -> pd.DataFrame:
    # GitHub-first: il disco di Streamlit Cloud è effimero, quindi la fonte di
    # verità è il repo. Il disco locale resta solo come fallback di emergenza.
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
            df[col] = "" if (col.startswith("Nota") or col in ("Screenshot", "Origine")) else 0

    df = df[COLONNE_ATTESE]

    for col in COLONNE_ATTESE:
        if col.startswith("Nota") or col in ("Screenshot", "Origine"):
            df[col] = df[col].fillna("").astype(str).replace("nan", "")

    # Default Origine = manuale: protegge tutti i titoli già presenti dall'automazione.
    df["Origine"] = df["Origine"].replace("", "manuale")

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
    # NOTA: salva_riga è chiamata SOLO da percorsi manuali (Gemini, form, editing UI).
    # Quindi ogni riga che passa di qui è, per definizione, "manuale" (sacra).
    df = carica_watchlist()
    ticker = ticker.strip().upper()

    if ticker in df["Ticker"].str.upper().values:
        idx = df[df["Ticker"].str.upper() == ticker].index[0]
        for col in ["Nota 1", "Nota 2", "Nota 3", "Nota VWAP 1", "Nota VWAP 2", "Nota VWAP 3", "Screenshot", "Origine", "Nota POC"]:
            df[col] = df[col].astype(object)

        df.at[idx, "Livello 1"] = l1; df.at[idx, "Nota 1"] = n1
        df.at[idx, "Livello 2"] = l2; df.at[idx, "Nota 2"] = n2
        df.at[idx, "Livello 3"] = l3; df.at[idx, "Nota 3"] = n3
        df.at[idx, "VWAP 1"] = v1; df.at[idx, "Nota VWAP 1"] = nv1
        df.at[idx, "VWAP 2"] = v2; df.at[idx, "Nota VWAP 2"] = nv2
        df.at[idx, "VWAP 3"] = v3; df.at[idx, "Nota VWAP 3"] = nv3
        # Se ci metti mano tu, diventa tuo: l'auto-pulizia non lo toccherà più.
        df.at[idx, "Origine"] = "manuale"

        if screenshot_path:
            df.at[idx, "Screenshot"] = screenshot_path
    else:
        nuova_riga = pd.DataFrame([{
            "Ticker": ticker,
            "Livello 1": l1, "Nota 1": n1, "Livello 2": l2, "Nota 2": n2, "Livello 3": l3, "Nota 3": n3,
            "VWAP 1": v1, "Nota VWAP 1": nv1, "VWAP 2": v2, "Nota VWAP 2": nv2, "VWAP 3": v3, "Nota VWAP 3": nv3,
            "Screenshot": screenshot_path or "",
            "Origine": "manuale",
            "POC": 0,
            "Nota POC": "",
        }])
        df = pd.concat([df, nuova_riga], ignore_index=True)

    df.to_csv(CSV_PATH, index=False)
    commit_csv_su_github(df)
    return df

# ---------------------------------------------------------------
# UI
# ---------------------------------------------------------------
st.title("📊 Watchlist da Screenshot")

# ---------------------------------------------------------------
# AUTOMAZIONE SCREENER (info) — l'import manuale via CSV è stato rimosso:
# ora i titoli entrano/escono da soli dalla pagina Screening (vedi watchlist_io).
# ---------------------------------------------------------------
st.info(
    "🔗 **Automazione attiva dalla pagina Screening.** I titoli dello screener che toccano "
    "un POC o un VWAP entrano **da soli** nella watchlist con origine `auto` (🤖) e vengono "
    "rimossi quando escono dalla zona. I titoli che inserisci o modifichi a mano qui hanno "
    "origine `manuale` e **non vengono mai toccati** dall'automazione."
)

col_upload, col_result = st.columns([1, 1])

with col_upload:
    uploaded_file = st.file_uploader(
        "Carica screenshot del grafico", type=["png", "jpg", "jpeg", "webp"]
    )

    if uploaded_file is not None:
        st.image(uploaded_file, caption="Screenshot caricato", use_container_width=True)

        if st.button("🔍 Analizza con Gemini", type="primary"):
            with st.spinner("Analisi in corso..."):
                try:
                    image_bytes = uploaded_file.getvalue()
                    mime_type = uploaded_file.type
                    dati = analizza_immagine(image_bytes, mime_type)
                    st.session_state["ultima_analisi"] = dati
                    st.success("Analisi completata.")
                except Exception as e:
                    st.error(f"Errore durante l'analisi: {e}")

with col_result:
    if "ultima_analisi" in st.session_state:
        dati = st.session_state["ultima_analisi"]
        st.subheader("Risultato estratto")

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

        if st.button("💾 Salva in watchlist"):
            screenshot_path = None
            if uploaded_file is not None:
                estensione = uploaded_file.type.split("/")[-1] if uploaded_file.type else "png"
                screenshot_path = carica_screenshot_su_github(
                    ticker_edit.strip().upper() or "TICKER", uploaded_file.getvalue(), estensione
                )
            salva_riga(ticker_edit, l1_edit, l2_edit, l3_edit, v1_edit, v2_edit, v3_edit,
                       n1_edit, n2_edit, n3_edit, nv1_edit, nv2_edit, nv3_edit, screenshot_path)
            del st.session_state["ultima_analisi"]
            st.rerun()

# ---------------------------------------------------------------
# INSERIMENTO MANUALE
# ---------------------------------------------------------------
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

        m_submit = st.form_submit_button("💾 Salva Ticker Manuale")

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

# ---------------------------------------------------------------
# TABELLA + GRAFICO
# ---------------------------------------------------------------
st.subheader("📋 Watchlist salvata")
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
        r = requests.get(
            "https://api.twelvedata.com/time_series",
            params={
                "symbol": simbolo, "interval": interval, "outputsize": outputsize,
                "apikey": TD_API_KEY, "order": "ASC",
            },
        )
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
        df = df.rename(columns={
            "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume",
        })
        return df.dropna(subset=["Close"])
    except Exception as e:
        _ULTIMO_ERRORE_TD = str(e)
        print(f"Errore Twelve Data per {simbolo}: {e}")
        return pd.DataFrame()

def determina_exchange(simbolo: str) -> str:
    return "nasdaq"

@st.cache_data(ttl=300)
def carica_prezzi_condivisi() -> dict:
    path = "prezzi_attuali.json"
    if GITHUB_TOKEN and GITHUB_REPO:
        try:
            r = requests.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}",
                headers={"Authorization": f"token {GITHUB_TOKEN}"},
            )
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
    ricerca = st.text_input(
        "Cerca ticker", placeholder="🔍 Cerca ticker...", label_visibility="collapsed"
    )
    df_visualizzata = df[df["Ticker"].str.contains(ricerca.strip(), case=False, na=False)] if ricerca else df

    if not df_visualizzata.empty:
        df_visualizzata = df_visualizzata.drop_duplicates(subset=["Ticker"], keep="last").reset_index(drop=True)

    # 13 colonne: Ticker, L1, L2, L3, V1, V2, V3, Prezzo, Azioni (5)
    COLS = [2, 1, 1, 1, 1, 1, 1, 1, 0.3, 0.3, 0.3, 0.3, 0.3]
    h1, h2, h3_, h4, h5, h6, h7, h8, h9, h10, h11, h12, h13 = st.columns(COLS)
    etichette = zip(
        (h1, h2, h3_, h4, h5, h6, h7, h8),
        ("Ticker", "Livello 1", "Livello 2", "Livello 3", "VWAP 1", "VWAP 2", "VWAP 3", "Prezzo"),
    )
    for col, label in etichette:
        col.markdown(f'<div class="wl-header">{label}</div>', unsafe_allow_html=True)
    for col in (h9, h10, h11, h12, h13):
        col.markdown('<div class="wl-header">&nbsp;</div>', unsafe_allow_html=True)

    if df_visualizzata.empty:
        st.caption("Nessun ticker corrisponde alla ricerca.")

    def badge(valore, classe, nota=""):
        if pd.isna(valore) or valore == 0:
            return f'<span class="wl-badge empty">—</span>'
        title = f' title="{nota}"' if nota else ""
        icona = " 📝" if nota else ""
        return f'<span class="wl-badge {classe}"{title}>{valore:g}{icona}</span>'

    if "editing_ticker" not in st.session_state:
        st.session_state["editing_ticker"] = None

    prezzi_condivisi, prezzi_aggiornati_il = carica_prezzi_condivisi()
    if prezzi_aggiornati_il:
        st.caption(f"💹 Prezzi aggiornati da ultimo controllo alert: {prezzi_aggiornati_il}")

    for _, r in df_visualizzata.iterrows():
        ticker_riga = r["Ticker"]
        origine_riga = str(r.get("Origine", "manuale")).strip().lower()

        if st.session_state["editing_ticker"] == ticker_riga:
            c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11, c12, c13 = st.columns(COLS)
            nuovo_nome_ticker = c1.text_input("Ticker", value=ticker_riga, key=f"edit_ticker_{ticker_riga}_{_}", label_visibility="collapsed")
            nl1 = c2.number_input("L1", value=float(r["Livello 1"]), key=f"edit_l1_{ticker_riga}_{_}", label_visibility="collapsed")
            nl2 = c3.number_input("L2", value=float(r["Livello 2"]), key=f"edit_l2_{ticker_riga}_{_}", label_visibility="collapsed")
            nl3 = c4.number_input("L3", value=float(r["Livello 3"]), key=f"edit_l3_{ticker_riga}_{_}", label_visibility="collapsed")
            nv1 = c5.number_input("V1", value=float(r["VWAP 1"]), key=f"edit_v1_{ticker_riga}_{_}", label_visibility="collapsed")
            nv2 = c6.number_input("V2", value=float(r["VWAP 2"]), key=f"edit_v2_{ticker_riga}_{_}", label_visibility="collapsed")
            nv3 = c7.number_input("V3", value=float(r["VWAP 3"]), key=f"edit_v3_{ticker_riga}_{_}", label_visibility="collapsed")
            for col in (c8, c9, c10):
                col.write("")

            if c11.button("💾", key=f"save_{ticker_riga}_{_}"):
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
            if c12.button("️", key=f"cancel_{ticker_riga}_{_}"):
                st.session_state["editing_ticker"] = None
                st.rerun()

            _, nc1, nc2, nc3, nc4, nc5, nc6, _ = st.columns([2, 1, 1, 1, 1, 1, 1, 2.7])
            nc1.text_input("Nota L1", value=str(r["Nota 1"] or ""), key=f"edit_n1_{ticker_riga}_{_}", label_visibility="collapsed")
            nc2.text_input("Nota L2", value=str(r["Nota 2"] or ""), key=f"edit_n2_{ticker_riga}_{_}", label_visibility="collapsed")
            nc3.text_input("Nota L3", value=str(r["Nota 3"] or ""), key=f"edit_n3_{ticker_riga}_{_}", label_visibility="collapsed")
            nc4.text_input("Nota V1", value=str(r["Nota VWAP 1"] or ""), key=f"edit_nv1_{ticker_riga}_{_}", label_visibility="collapsed")
            nc5.text_input("Nota V2", value=str(r["Nota VWAP 2"] or ""), key=f"edit_nv2_{ticker_riga}_{_}", label_visibility="collapsed")
            nc6.text_input("Nota V3", value=str(r["Nota VWAP 3"] or ""), key=f"edit_nv3_{ticker_riga}_{_}", label_visibility="collapsed")

        else:
            c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11, c12, c13 = st.columns(COLS)
            # Badge origine: 🤖 = auto (pulibile dall'automazione), niente = manuale (sacro)
            prefisso_origine = "🤖 " if origine_riga == "auto" else ""
            if c1.button(prefisso_origine + ticker_riga, key=f"select_{ticker_riga}_{_}", use_container_width=True):
                st.session_state["ticker_grafico"] = ticker_riga
                st.rerun()
            c2.markdown(badge(r["Livello 1"], "l1", r["Nota 1"]), unsafe_allow_html=True)
            c3.markdown(badge(r["Livello 2"], "l2", r["Nota 2"]), unsafe_allow_html=True)
            c4.markdown(badge(r["Livello 3"], "l3", r["Nota 3"]), unsafe_allow_html=True)
            c5.markdown(badge(r["VWAP 1"], "v1", r["Nota VWAP 1"]), unsafe_allow_html=True)
            c6.markdown(badge(r["VWAP 2"], "v2", r["Nota VWAP 2"]), unsafe_allow_html=True)
            c7.markdown(badge(r["VWAP 3"], "v3", r["Nota VWAP 3"]), unsafe_allow_html=True)

            ticker_td_riga = mappa_ticker_twelvedata(ticker_riga)
            prezzo_riga = prezzi_condivisi.get(ticker_riga)

            if prezzo_riga is not None:
                c8.markdown(
                    f'<span style="font-family:\'IBM Plex Mono\',monospace;font-weight:600;">{prezzo_riga:.2f}</span>',
                    unsafe_allow_html=True,
                )
            else:
                c8.markdown('<span style="color:#4a5568;">—</span>', unsafe_allow_html=True)

            tv_symbol = ticker_td_riga.replace('/', '')
            tv_url = f"https://www.tradingview.com/symbols/{tv_symbol}/"
            exch = determina_exchange(ticker_td_riga)
            fc_url = f"https://terminal.forecaster.biz/instrument/{exch}/{ticker_riga.lower()}/overview"
            c9.markdown(f'<a href="{tv_url}" target="_blank" style="text-decoration:none;">📈</a>', unsafe_allow_html=True)
            c10.markdown(f'<a href="{fc_url}" target="_blank" style="text-decoration:none;">🔮</a>', unsafe_allow_html=True)
            if r.get("Screenshot"):
                if c11.button("🖼️", key=f"screenshot_{ticker_riga}_{_}"):
                    st.session_state["screenshot_da_mostrare"] = r["Screenshot"]
                    st.rerun()
            else:
                c11.write("")
            if c12.button("✏️", key=f"edit_{ticker_riga}_{_}"):
                st.session_state["editing_ticker"] = ticker_riga
                st.rerun()
            if c13.button("🗑️", key=f"del_{ticker_riga}_{_}"):
                elimina_riga(ticker_riga)
                st.rerun()

    st.write("")

    if st.session_state.get("screenshot_da_mostrare"):
        path = st.session_state["screenshot_da_mostrare"]
        try:
            r_img = requests.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}",
                headers={"Authorization": f"token {GITHUB_TOKEN}"},
            )
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
            st.caption(f"Spazio repo usato: {dim_mb:.0f} MB / ~1000 MB consigliati")

    if "ticker_grafico" not in st.session_state or st.session_state["ticker_grafico"] not in df["Ticker"].values:
        st.session_state["ticker_grafico"] = df["Ticker"].iloc[0]
    ticker_selezionato = st.session_state["ticker_grafico"]

    riga = df[df["Ticker"] == ticker_selezionato].iloc[0]
    livelli = [float(riga[f"Livello {i}"]) for i in (1, 2, 3) if pd.notna(riga[f"Livello {i}"]) and riga[f"Livello {i}"] != 0]
    vwap = [float(riga[f"VWAP {i}"]) for i in (1, 2, 3) if pd.notna(riga[f"VWAP {i}"]) and riga[f"VWAP {i}"] != 0]

    import json as _json

    TIMEFRAMES = {
        "4H": ("4h", 300),
        "1D": ("1day", 500),
        "1W": ("1week", 260),
        "1M": ("1month", 120),
    }
    st.markdown(f'<h3 style="margin-bottom:0.4rem;">📈 {ticker_selezionato}</h3>', unsafe_allow_html=True)
    timeframe = st.radio(
        "Timeframe", list(TIMEFRAMES.keys()), index=1, horizontal=True, label_visibility="collapsed"
    )
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
            {
                "time": int(idx.timestamp()) if usa_timestamp else idx.strftime("%Y-%m-%d"),
                "open": round(r["Open"], 4),
                "high": round(r["High"], 4),
                "low": round(r["Low"], 4),
                "close": round(r["Close"], 4),
            }
            for idx, r in storico.iterrows()
        ]

        # Linee Livelli (continue)
        linee_livelli_js = "\n".join(
            f'candleSeries.createPriceLine({{price: {liv}, color: "{["#f0b90b", "#00c176", "#ff4d4d"][i % 3]}", lineWidth: 2, lineStyle: 0, title: "L{i+1}: {liv}"}});'
            for i, liv in enumerate(livelli)
        )
        # Linee VWAP (tratteggiate)
        linee_vwap_js = "\n".join(
            f'candleSeries.createPriceLine({{price: {v}, color: "#00b4d8", lineWidth: 2, lineStyle: 2, title: "V{i+1}: {v}"}});'
            for i, v in enumerate(vwap)
        )

        chart_html = f"""
        <div id="chart_container" style="width:100%; height:600px;"></div>
        <script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
        <script>
          const container = document.getElementById('chart_container');
          const chart = LightweightCharts.createChart(container, {{
            width: container.clientWidth,
            height: 600,
            layout: {{ background: {{ color: '#0e1117' }}, textColor: '#d1d4dc' }},
            grid: {{ vertLines: {{ color: '#1e222d' }}, horzLines: {{ color: '#1e222d' }} }},
            timeScale: {{ borderColor: '#485c7b', timeVisible: {str(usa_timestamp).lower()} }},
          }});

          const candleSeries = chart.addCandlestickSeries({{
            upColor: '#26a69a', downColor: '#ef5350',
            borderVisible: false, wickUpColor: '#26a69a', wickDownColor: '#ef5350',
          }});

          candleSeries.setData({_json.dumps(candele)});
          {linee_livelli_js}
          {linee_vwap_js}

          chart.timeScale().fitContent();
          new ResizeObserver(entries => {{ chart.applyOptions({{ width: entries[0].contentRect.width }}); }}).observe(container);
        </script>
        """
        st.components.v1.html(chart_html, height=620)

# ---------------------------------------------------------------
# STORICO ALERT
# ---------------------------------------------------------------
st.divider()
st.subheader("🕘 Storico Alert")

HISTORY_PATH = "alert_history.csv"

@st.cache_data(ttl=60)
def carica_storico_alert() -> pd.DataFrame:
    # Lo schema è cambiato (Livelli Toccati / Convergenza / Regime): read_csv lo
    # inferisce da solo, quindi questa funzione si adatta automaticamente.
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
    st.dataframe(
        storico_alert.sort_values("Data", ascending=False),
        use_container_width=True,
        hide_index=True,
    )
