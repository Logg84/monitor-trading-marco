import streamlit as st
import pandas as pd
import os
from PIL import Image
from google import genai
from google.genai import types

CSV_PATH = "watchlist.csv"
MODEL_NAME = "gemini-2.5-flash"  # se non disponibile, provare "gemini-2.0-flash"

st.set_page_config(page_title="Watchlist Grafici", layout="wide")

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

COLONNE_ATTESE = ["Ticker", "Livello 1", "Livello 2", "Livello 3"]

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
            df[col] = 0

    df = df[COLONNE_ATTESE]  # ordina/filtra colonne, scarta extra

    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated()]

    return df


def salva_riga(ticker: str, l1: float, l2: float, l3: float):
    df = carica_watchlist()
    ticker = ticker.strip().upper()

    if ticker in df["Ticker"].str.upper().values:
        # Ticker già presente: sovrascrive i livelli sulla riga esistente
        idx = df[df["Ticker"].str.upper() == ticker].index[0]
        df.loc[idx, ["Livello 1", "Livello 2", "Livello 3"]] = [l1, l2, l3]
    else:
        nuova_riga = pd.DataFrame(
            [{"Ticker": ticker, "Livello 1": l1, "Livello 2": l2, "Livello 3": l3}]
        )
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
        l2_edit = st.number_input("Livello 2", value=float(dati.get("livello_2", 0) or 0))
        l3_edit = st.number_input("Livello 3", value=float(dati.get("livello_3", 0) or 0))

        if st.button("💾 Salva in watchlist"):
            salva_riga(ticker_edit, l1_edit, l2_edit, l3_edit)
            del st.session_state["ultima_analisi"]
            st.rerun()

st.divider()

# ---------------------------------------------------------------
# TABELLA + GRAFICO CON LIVELLI DISEGNATI (Lightweight Charts)
# ---------------------------------------------------------------
st.subheader("📋 Watchlist salvata")
df = carica_watchlist()

CRYPTO_NOTE = {"BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "BNB", "LTC"}


def mappa_ticker_yfinance(ticker: str) -> str:
    t = ticker.strip().upper()
    for base in CRYPTO_NOTE:
        if t == f"{base}USD":
            return f"{base}-USD"
    if len(t) == 6 and t.isalpha() and t[:3] not in CRYPTO_NOTE:
        return f"{t}=X"
    return t


def elimina_riga(ticker: str):
    df = carica_watchlist()
    df = df[df["Ticker"] != ticker]
    df.to_csv(CSV_PATH, index=False)
    commit_csv_su_github(df)


if df.empty or "Ticker" not in df.columns:
    st.info("Nessun dato salvato ancora.")
else:
    st.write("**Watchlist:**")
    for _, r in df.iterrows():
        c1, c2, c3, c4, c5 = st.columns([2, 1.5, 1.5, 1.5, 0.8])
        c1.write(r["Ticker"])
        c2.write(r["Livello 1"])
        c3.write(r["Livello 2"])
        c4.write(r["Livello 3"])
        if c5.button("🗑️", key=f"del_{r['Ticker']}"):
            elimina_riga(r["Ticker"])
            st.rerun()

    ticker_selezionato = st.selectbox("Seleziona ticker per il grafico", df["Ticker"].unique())
    riga = df[df["Ticker"] == ticker_selezionato].iloc[0]
    livelli = [
        float(riga[f"Livello {i}"])
        for i in (1, 2, 3)
        if pd.notna(riga[f"Livello {i}"]) and riga[f"Livello {i}"] != 0
    ]

    import yfinance as yf
    import json as _json

    ticker_yf = mappa_ticker_yfinance(ticker_selezionato)
    storico = yf.Ticker(ticker_yf).history(period="6mo", interval="1d")

    if storico.empty:
        st.warning(f"Nessun dato storico trovato per {ticker_selezionato} ({ticker_yf}).")
    else:
        candele = [
            {
                "time": idx.strftime("%Y-%m-%d"),
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
            timeScale: {{ borderColor: '#485c7b' }},
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
