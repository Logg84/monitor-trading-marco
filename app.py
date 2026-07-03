import streamlit as st
import pandas as pd
import os
import datetime
import time
import yfinance as yf
from PIL import Image
from google import genai
from google.genai import types

CSV_PATH = "watchlist.csv"
MODEL_NAME = "gemini-2.5-flash"  # se non disponibile, provare "gemini-2.0-flash"

st.set_page_config(page_title="Watchlist Grafici", layout="wide", page_icon="📈")

# ---------------------------------------------------------------
# STILE — palette coerente con le linee del grafico (giallo/verde/rosso),
# font monospace per i numeri (leggibilità dati), spaziature ridotte.
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

/* Riga watchlist come card */
div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
    display: flex; align-items: center;
}

.wl-ticker {
    font-family: 'IBM Plex Mono', monospace; font-weight: 600; font-size: 0.95rem;
    color: #e8eaed; letter-spacing: 0.02em;
}

.wl-badge {
    font-family: 'IBM Plex Mono', monospace; font-size: 0.82rem; font-weight: 600;
    padding: 3px 10px; border-radius: 6px; display: inline-block;
    border: 1px solid transparent;
}
.wl-badge.l1 { color: #f0b90b; background: rgba(240,185,11,0.10); border-color: rgba(240,185,11,0.25); }
.wl-badge.l2 { color: #00c176; background: rgba(0,193,118,0.10); border-color: rgba(0,193,118,0.25); }
.wl-badge.l3 { color: #ff4d4d; background: rgba(255,77,77,0.10); border-color: rgba(255,77,77,0.25); }
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
# CLIENT GEMINI (nuovo SDK ufficiale, NON google-generativeai)
# ---------------------------------------------------------------
@st.cache_resource
def get_client():
    api_key = st.secrets["GEMINI_API_KEY"]
    return genai.Client(api_key=api_key)

client = get_client()

# Schema JSON che Gemini DEVE rispettare -> niente parsing fragile
RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "ticker": {"type": "STRING"},
        "livello_1": {"type": "NUMBER"},
        "livello_2": {"type": "NUMBER"},
        "livello_3": {"type": "NUMBER"},
    },
    "required": ["ticker"],
}

PROMPT = """Analizza questo screenshot di un grafico finanziario (piattaforma di trading).
Estrai:
1. Il ticker/simbolo dello strumento (es. AAPL, EURUSD, BTCUSD). Se non è scritto esplicitamente,
   deducilo dal contesto del grafico (candele, valuta, watermark).
2. Fino a 3 livelli di prezzo numerici rilevanti visibili sul grafico (supporti, resistenze,
   linee orizzontali disegnate, prezzo corrente). Se ne trovi meno di 3, lascia gli altri a 0.
Rispondi SOLO con i dati richiesti, nessun testo aggiuntivo."""


def analizza_immagine(image_bytes: bytes, mime_type: str) -> dict:
    """Chiama Gemini con SDK ufficiale e ritorna un dict già parsato."""
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
                types.SafetySetting(
                    category="HARM_CATEGORY_DANGEROUS_CONTENT",
                    threshold="BLOCK_NONE",
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_HARASSMENT",
                    threshold="BLOCK_NONE",
                ),
            ],
        ),
    )

    # DIAGNOSTICA: se Gemini blocca la risposta, lo vediamo qui invece di un KeyError cieco
    if not response.candidates:
        raise ValueError(
            f"Nessuna risposta da Gemini. Prompt feedback: {response.prompt_feedback}"
        )

    candidate = response.candidates[0]
    if candidate.finish_reason not in ("STOP", 1):  # 1 = STOP nell'enum
        raise ValueError(f"Risposta bloccata. finish_reason={candidate.finish_reason}")

    import json
    return json.loads(response.text)


# ---------------------------------------------------------------
# CSV: lettura / scrittura
# ---------------------------------------------------------------
import base64
import requests

COLONNE_ATTESE = ["Ticker", "Livello 1", "Nota 1", "Livello 2", "Nota 2", "Livello 3", "Nota 3", "Screenshot"]

GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN")
GITHUB_REPO = st.secrets.get("GITHUB_REPO")  # es. "Logg84/monitor-trading-marco"


def commit_csv_su_github(df: pd.DataFrame):
    """Scrive watchlist.csv direttamente nel repo GitHub via Contents API,
    così i dati sopravvivono al riavvio/sleep del container Streamlit Cloud."""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return  # secrets non configurati: salva solo in locale (non persistente)

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{CSV_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    # Serve lo sha del file esistente per fare un update (non una creazione)
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
    """Salva lo screenshot originale nel repo, cartella screenshots/. Ritorna il path salvato."""
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
    """Dimensione totale del repo in KB, per avvisare prima di avvicinarsi ai limiti pratici di GitHub."""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return None
    try:
        r = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}",
            headers={"Authorization": f"token {GITHUB_TOKEN}"},
        )
        if r.status_code == 200:
            return r.json().get("size")  # GitHub restituisce già in KB
    except Exception:
        pass
    return None

# Mappa colonne vecchie/alternative -> nuovo schema, per evitare KeyError
# se il CSV nel repo è stato creato da una versione precedente dell'app.
ALIAS_COLONNE = {
    "ticker": "Ticker",
    "livello": "Livello 1",
    "livello_1": "Livello 1",
    "livello_2": "Livello 2",
    "livello_3": "Livello 3",
}


def carica_watchlist() -> pd.DataFrame:
    if not os.path.exists(CSV_PATH):
        return pd.DataFrame(columns=COLONNE_ATTESE)

    df = pd.read_csv(CSV_PATH)

    # Migrazione automatica: rinomina eventuali colonne con schema vecchio
    df = df.rename(columns=ALIAS_COLONNE)

    # Aggiunge colonne mancanti (es. Livello 2/3 se il vecchio CSV ne aveva solo una)
    for col in COLONNE_ATTESE:
        if col not in df.columns:
            df[col] = "" if (col.startswith("Nota") or col == "Screenshot") else 0

    df = df[COLONNE_ATTESE]  # ordina/filtra colonne, scarta extra

    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated()]

    return df


def salva_riga(ticker: str, l1: float, l2: float, l3: float, n1: str = "", n2: str = "", n3: str = "", screenshot_path: str = None):
    df = carica_watchlist()
    ticker = ticker.strip().upper()

    if ticker in df["Ticker"].str.upper().values:
        idx = df[df["Ticker"].str.upper() == ticker].index[0]
        df.loc[idx, ["Livello 1", "Nota 1", "Livello 2", "Nota 2", "Livello 3", "Nota 3"]] = [
            l1, n1, l2, n2, l3, n3
        ]
        if screenshot_path:  # aggiorna lo screenshot solo se ne è stato caricato uno nuovo
            df.loc[idx, "Screenshot"] = screenshot_path
    else:
        nuova_riga = pd.DataFrame([{
            "Ticker": ticker, "Livello 1": l1, "Nota 1": n1,
            "Livello 2": l2, "Nota 2": n2, "Livello 3": l3, "Nota 3": n3,
            "Screenshot": screenshot_path or "",
        }])
        df = pd.concat([df, nuova_riga], ignore_index=True)

    df.to_csv(CSV_PATH, index=False)
    commit_csv_su_github(df)
    return df


# ---------------------------------------------------------------
# UI
# ---------------------------------------------------------------
st.title("📊 Watchlist da Screenshot")

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
                    mime_type = uploaded_file.type  # es. image/png
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
        l1_edit = st.number_input("Livello 1", value=float(dati.get("livello_1", 0) or 0))
        n1_edit = st.text_input("Nota Livello 1 (opzionale)", value="", placeholder="es. supporto storico")
        l2_edit = st.number_input("Livello 2", value=float(dati.get("livello_2", 0) or 0))
        n2_edit = st.text_input("Nota Livello 2 (opzionale)", value="", placeholder="es. media mobile 200")
        l3_edit = st.number_input("Livello 3", value=float(dati.get("livello_3", 0) or 0))
        n3_edit = st.text_input("Nota Livello 3 (opzionale)", value="", placeholder="es. resistenza ATH")

        if st.button("💾 Salva in watchlist"):
            screenshot_path = None
            if uploaded_file is not None:
                estensione = uploaded_file.type.split("/")[-1] if uploaded_file.type else "png"
                screenshot_path = carica_screenshot_su_github(
                    ticker_edit.strip().upper() or "TICKER", uploaded_file.getvalue(), estensione
                )
            salva_riga(ticker_edit, l1_edit, l2_edit, l3_edit, n1_edit, n2_edit, n3_edit, screenshot_path)
            del st.session_state["ultima_analisi"]
            st.rerun()

st.divider()

# ---------------------------------------------------------------
# TABELLA + GRAFICO CON LIVELLI DISEGNATI (Lightweight Charts)
# ---------------------------------------------------------------
st.subheader("📋 Watchlist salvata")
df = carica_watchlist()

@st.cache_data(ttl=86400)
def determina_exchange(ticker_yf: str) -> str:
    """Recupera l'exchange reale via yfinance, cache 24h per non rallentare l'app."""
    mappa_exchange = {
        "NMS": "nasdaq", "NGM": "nasdaq", "NCM": "nasdaq",
        "NYQ": "nyse", "ASE": "amex", "PCX": "amex",
    }
    try:
        info = yf.Ticker(ticker_yf).info
        codice = info.get("exchange", "")
        return mappa_exchange.get(codice, "nasdaq")
    except Exception:
        return "nasdaq"


CRYPTO_NOTE = {"BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "BNB", "LTC"}


def mappa_ticker_yfinance(ticker: str) -> str:
    t = ticker.strip().upper()
    for base in CRYPTO_NOTE:
        if t == f"{base}USD":
            return f"{base}-USD"
    if len(t) == 6 and t.isalpha() and t[:3] not in CRYPTO_NOTE:
        return f"{t}=X"
    return t


@st.cache_data(ttl=120)
def dati_prezzo_trend(ticker_yf: str) -> dict:
    """Prezzo attuale + variazione % ultimi 7gg e ultimi 30gg (un'unica chiamata)."""
    try:
        h = yf.Ticker(ticker_yf).history(period="3mo", interval="1d")
        if h.empty:
            return {}
        prezzo = float(h["Close"].iloc[-1])
        chiusure = h["Close"]
        var_1s = ((prezzo / chiusure.iloc[-6]) - 1) * 100 if len(chiusure) > 6 else None
        var_1m = ((prezzo / chiusure.iloc[-22]) - 1) * 100 if len(chiusure) > 22 else None
        return {"prezzo": prezzo, "var_1s": var_1s, "var_1m": var_1m}
    except Exception:
        return {}


@st.cache_data(ttl=86400)
def stagionalita_mensile(ticker_yf: str) -> dict:
    """Rendimento medio storico (fino a 15 anni) per il mese precedente/attuale/successivo."""
    try:
        h = yf.Ticker(ticker_yf).history(period="15y", interval="1mo")
        if h.empty or len(h) < 12:
            return {}
        rendimenti = h["Close"].pct_change().dropna() * 100
        rendimenti_per_mese = rendimenti.groupby(rendimenti.index.month).mean()

        oggi = datetime.date.today()
        mese_prec = 12 if oggi.month == 1 else oggi.month - 1
        mese_succ = 1 if oggi.month == 12 else oggi.month + 1

        return {
            "prec": rendimenti_per_mese.get(mese_prec),
            "att": rendimenti_per_mese.get(oggi.month),
            "succ": rendimenti_per_mese.get(mese_succ),
        }
    except Exception:
        return {}


def span_variazione(valore, con_freccia=True) -> str:
    if valore is None or pd.isna(valore):
        return '<span style="color:#4a5568;">—</span>'
    colore = "#00c176" if valore >= 0 else "#ff4d4d"
    freccia = ("▲" if valore >= 0 else "▼") if con_freccia else ""
    return f'<span style="color:{colore}; font-family:\'IBM Plex Mono\',monospace; font-size:0.8rem;">{freccia} {valore:+.1f}%</span>'


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

    COLS = [2, 1.3, 1.3, 1.3, 1, 1.3, 2.2, 0.4, 0.4, 0.4, 0.4, 0.4]
    h1, h2, h3_, h4, h5, h6, h7, h8, h9, h10, h11, h12 = st.columns(COLS)
    etichette = zip(
        (h1, h2, h3_, h4, h5, h6, h7),
        ("Ticker", "Livello 1", "Livello 2", "Livello 3", "Prezzo", "Trend 1S/1M", "Stagion. (prec/att/succ)"),
    )
    for col, label in etichette:
        col.markdown(f'<div class="wl-header">{label}</div>', unsafe_allow_html=True)
    for col in (h8, h9, h10, h11, h12):
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

    for _, r in df_visualizzata.iterrows():
        ticker_riga = r["Ticker"]

        if st.session_state["editing_ticker"] == ticker_riga:
            c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11, c12 = st.columns(COLS)
            c1.markdown(f'<span class="wl-ticker">{ticker_riga}</span>', unsafe_allow_html=True)
            nl1 = c2.number_input("L1", value=float(r["Livello 1"]), key=f"edit_l1_{ticker_riga}", label_visibility="collapsed")
            nl2 = c3.number_input("L2", value=float(r["Livello 2"]), key=f"edit_l2_{ticker_riga}", label_visibility="collapsed")
            nl3 = c4.number_input("L3", value=float(r["Livello 3"]), key=f"edit_l3_{ticker_riga}", label_visibility="collapsed")
            for col in (c5, c6, c7, c8):
                col.write("")
            if c11.button("💾", key=f"save_{ticker_riga}"):
                salva_riga(
                    ticker_riga, nl1, nl2, nl3,
                    st.session_state.get(f"edit_n1_{ticker_riga}", r["Nota 1"]),
                    st.session_state.get(f"edit_n2_{ticker_riga}", r["Nota 2"]),
                    st.session_state.get(f"edit_n3_{ticker_riga}", r["Nota 3"]),
                )
                st.session_state["editing_ticker"] = None
                st.rerun()
            if c12.button("✖️", key=f"cancel_{ticker_riga}"):
                st.session_state["editing_ticker"] = None
                st.rerun()

            _, nc1, nc2, nc3, _ = st.columns([2, 1.3, 1.3, 1.3, 5.3])
            nc1.text_input("Nota L1", value=str(r["Nota 1"] or ""), key=f"edit_n1_{ticker_riga}", label_visibility="collapsed", placeholder="nota livello 1")
            nc2.text_input("Nota L2", value=str(r["Nota 2"] or ""), key=f"edit_n2_{ticker_riga}", label_visibility="collapsed", placeholder="nota livello 2")
            nc3.text_input("Nota L3", value=str(r["Nota 3"] or ""), key=f"edit_n3_{ticker_riga}", label_visibility="collapsed", placeholder="nota livello 3")
        else:
            c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11, c12 = st.columns(COLS)
            if c1.button(ticker_riga, key=f"select_{ticker_riga}", use_container_width=True):
                st.session_state["ticker_grafico"] = ticker_riga
                st.rerun()
            c2.markdown(badge(r["Livello 1"], "l1", r["Nota 1"]), unsafe_allow_html=True)
            c3.markdown(badge(r["Livello 2"], "l2", r["Nota 2"]), unsafe_allow_html=True)
            c4.markdown(badge(r["Livello 3"], "l3", r["Nota 3"]), unsafe_allow_html=True)

            ticker_yf_riga = mappa_ticker_yfinance(ticker_riga)
            pt = dati_prezzo_trend(ticker_yf_riga)
            stag = stagionalita_mensile(ticker_yf_riga)

            if pt.get("prezzo") is not None:
                c5.markdown(
                    f'<span style="font-family:\'IBM Plex Mono\',monospace;font-weight:600;">{pt["prezzo"]:.2f}</span>',
                    unsafe_allow_html=True,
                )
            else:
                c5.markdown('<span style="color:#4a5568;">—</span>', unsafe_allow_html=True)

            c6.markdown(
                f'{span_variazione(pt.get("var_1s"))}&nbsp;/&nbsp;{span_variazione(pt.get("var_1m"))}',
                unsafe_allow_html=True,
            )

            c7.markdown(
                f'{span_variazione(stag.get("prec"), con_freccia=False)}&nbsp;'
                f'{span_variazione(stag.get("att"), con_freccia=False)}&nbsp;'
                f'{span_variazione(stag.get("succ"), con_freccia=False)}',
                unsafe_allow_html=True,
            )

            tv_symbol = ticker_yf_riga.replace('=X', '').replace('-', '')
            tv_url = f"https://www.tradingview.com/symbols/{tv_symbol}/"
            exch = determina_exchange(ticker_yf_riga)
            fc_url = f"https://terminal.forecaster.biz/instrument/{exch}/{ticker_riga.lower()}/overview"
            c8.markdown(f'<a href="{tv_url}" target="_blank" style="text-decoration:none;">📈</a>', unsafe_allow_html=True)
            c9.markdown(f'<a href="{fc_url}" target="_blank" style="text-decoration:none;">🔮</a>', unsafe_allow_html=True)
            if r.get("Screenshot"):
                if c10.button("🖼️", key=f"screenshot_{ticker_riga}"):
                    st.session_state["screenshot_da_mostrare"] = r["Screenshot"]
                    st.rerun()
            else:
                c10.write("")
            if c11.button("✏️", key=f"edit_{ticker_riga}"):
                st.session_state["editing_ticker"] = ticker_riga
                st.rerun()
            if c12.button("🗑️", key=f"del_{ticker_riga}"):
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

    # Contatore dimensione repo — GitHub non ha un hard-limit rigido, ma oltre
    # 1GB le performance calano; avviso per tempo prima di arrivarci.
    dim_kb = dimensione_repo_kb()
    if dim_kb is not None:
        dim_mb = dim_kb / 1024
        soglia_mb = 800
        if dim_mb >= soglia_mb:
            st.warning(f"⚠️ Il repo occupa {dim_mb:.0f} MB, si sta avvicinando al limite consigliato (~1 GB). Valuta di ripulire vecchi screenshot.")
        else:
            st.caption(f"Spazio repo usato: {dim_mb:.0f} MB / ~1000 MB consigliati")

    # Ticker selezionato cliccando sul nome nella lista sopra (default: primo della lista)
    if "ticker_grafico" not in st.session_state or st.session_state["ticker_grafico"] not in df["Ticker"].values:
        st.session_state["ticker_grafico"] = df["Ticker"].iloc[0]
    ticker_selezionato = st.session_state["ticker_grafico"]

    riga = df[df["Ticker"] == ticker_selezionato].iloc[0]
    livelli = [
        float(riga[f"Livello {i}"])
        for i in (1, 2, 3)
        if pd.notna(riga[f"Livello {i}"]) and riga[f"Livello {i}"] != 0
    ]

    import json as _json

    # (period_yfinance, interval_yfinance, resample_pandas)
    # Il resample serve solo per 4H, che yfinance non offre nativamente.
    TIMEFRAMES = {
        "4H": ("730d", "60m", "4h"),   # limite Yahoo per dati orari: ~2 anni, non aggirabile
        "1D": ("10y", "1d", None),
        "1W": ("10y", "1wk", None),
        "1M": ("max", "1mo", None),
    }
    st.markdown(f'<h3 style="margin-bottom:0.4rem;">📈 {ticker_selezionato}</h3>', unsafe_allow_html=True)
    timeframe = st.radio(
        "Timeframe", list(TIMEFRAMES.keys()), index=1, horizontal=True, label_visibility="collapsed"
    )
    periodo, intervallo, resample_a = TIMEFRAMES[timeframe]

    ticker_yf = mappa_ticker_yfinance(ticker_selezionato)
    storico = yf.Ticker(ticker_yf).history(period=periodo, interval=intervallo)

    if resample_a and not storico.empty:
        storico = storico.resample(resample_a).agg({
            "Open": "first", "High": "max", "Low": "min", "Close": "last",
        }).dropna()

    if storico.empty:
        st.warning(f"Nessun dato storico trovato per {ticker_selezionato} ({ticker_yf}).")
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

        colori_livelli = ["#f0b90b", "#00c176", "#ff4d4d"]
        linee_js = "\n".join(
            f'candleSeries.createPriceLine({{'
            f'price: {liv}, color: "{colori_livelli[i % 3]}", '
            f'lineWidth: 2, lineStyle: 2, '
            f'title: "Livello {i+1}: {liv}" }});'
            for i, liv in enumerate(livelli)
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
            grid: {{
              vertLines: {{ color: '#1e222d' }},
              horzLines: {{ color: '#1e222d' }},
            }},
            timeScale: {{ borderColor: '#485c7b', timeVisible: {str(usa_timestamp).lower()} }},
          }});

          const candleSeries = chart.addCandlestickSeries({{
            upColor: '#26a69a', downColor: '#ef5350',
            borderVisible: false,
            wickUpColor: '#26a69a', wickDownColor: '#ef5350',
          }});

          candleSeries.setData({_json.dumps(candele)});

          {linee_js}

          chart.timeScale().fitContent();

          new ResizeObserver(entries => {{
            chart.applyOptions({{ width: entries[0].contentRect.width }});
          }}).observe(container);
        </script>
        """
        st.components.v1.html(chart_html, height=620)


# ---------------------------------------------------------------
# STORICO ALERT — letto direttamente da GitHub (non dal disco locale
# dell'app, che si aggiorna solo al riavvio) così è sempre aggiornato
# anche se l'ultimo alert è arrivato pochi minuti fa via GitHub Actions.
# ---------------------------------------------------------------
st.divider()
st.subheader("🕘 Storico Alert")

HISTORY_PATH = "alert_history.csv"


@st.cache_data(ttl=60)
def carica_storico_alert() -> pd.DataFrame:
    colonne = ["Data", "Ticker", "Livello", "Valore Livello", "Nota", "Prezzo al momento"]

    if GITHUB_TOKEN and GITHUB_REPO:
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{HISTORY_PATH}"
            headers = {"Authorization": f"token {GITHUB_TOKEN}"}
            r = requests.get(url, headers=headers)
            if r.status_code == 200:
                import io
                contenuto = base64.b64decode(r.json()["content"]).decode()
                return pd.read_csv(io.StringIO(contenuto))
        except Exception:
            pass  # fallback sotto

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
