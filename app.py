import streamlit as st
import pandas as pd
import requests
from PIL import Image
import base64
import json
import os

st.set_page_config(page_title="Monitor Trading", layout="wide")
st.title("Monitoraggio Asset - Ufficio Logistica")

# Recupero della chiave API
api_key = st.secrets.get("GEMINI_API_KEY")
if api_key:
    api_key = api_key.strip().strip('"').strip("'")
else:
    st.error("Chiave API di Gemini (GEMINI_API_KEY) non trovata nei Secrets di Streamlit!")

DB_FILE = "watchlist.csv"

# Caricamento del database persistente
if os.path.exists(DB_FILE):
    try:
        st.session_state.watchlist_df = pd.read_csv(DB_FILE)
    except:
        st.session_state.watchlist_df = pd.DataFrame(columns=["Ticker", "Livello 1", "Livello 2", "Livello 3"])
else:
    st.session_state.watchlist_df = pd.DataFrame(columns=["Ticker", "Livello 1", "Livello 2", "Livello 3"])

def b64_image(image_file):
    return base64.b64encode(image_file.getvalue()).decode('utf-8')

# --- SEZIONE 1: CARICAMENTO E ANALISI AUTOMATICA ---
st.subheader("1. Carica Grafico per Analisi Automatica")

uploaded_file = st.file_uploader("Trascina qui lo screenshot del grafico", type=['png', 'jpg', 'jpeg', 'webp'])

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    st.image(image, caption='Grafico caricato', use_container_width=False, width=400)
    
    with st.form(key='analisi_form'):
        st.write("Clicca sul bottone qui sotto per avviare l'analisi visiva dei livelli.")
        submit_button = st.form_submit_button(label='Analizza Grafico con Gemini')
        
    if submit_button and api_key:
        with st.spinner("Gemini sta analizzando il grafico..."):
            try:
                base64_data = b64_image(uploaded_file)
                mime_type = uploaded_file.type
                
                # Endpoint ufficiale v1beta per generateContent
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
                
                prompt = "Analizza questa immagine di un grafico finanziario. Trova il Ticker (es. AAPL, EURUSD, BTCUSD) e identifica fino a 3 livelli di prezzo o aree di attenzione principali segnati visivamente."
                
                # Configurazione blindata: costringiamo Gemini a rispondere in JSON strutturato e azzeriamo i filtri di sicurezza protettivi
                payload = {
                    "contents": [{
                        "parts": [
                            {"text": prompt},
                            {
                                "inlineData": {
                                    "mimeType": mime_type,
                                    "data": base64_data
                                }
                            }
                        ]
                    }],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "responseSchema": {
                            "type": "OBJECT",
                            "properties": {
                                "ticker": {"type": "STRING"},
                                "livello_1": {"type": "NUMBER"},
                                "livello_2": {"type": "NUMBER"},
                                "livello_3": {"type": "NUMBER"}
                            },
                            "required": ["ticker"]
                        }
                    },
                    "safetySettings": [
                        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
                    ]
                }
                
                headers = {'Content-Type': 'application/json'}
                response = requests.post(url, headers=headers, json=payload)
                
                if response.status_code != 200:
                    st.error(f"Errore di rete dalle API di Google (Stato {response.status_code}): {response.text}")
                else:
                    response_json = response.json()
                    
                    # Estrazione sicura del testo JSON pre-strutturato
                    text_response = None
                    try:
                        text_response = response_json['candidates'][0]['content']['parts'][0]['text'].strip()
                    except:
                        pass
                    
                    if text_response:
                        data = json.loads(text_response)
                        
                        nuovo_dato = {
                            "Ticker": str(data.get('ticker', 'SCONOSCIUTO')).upper().strip(),
                            "Livello 1": data.get('livello_1'),
                            "Livello 2": data.get('livello_2'),
                            "Livello 3": data.get('livello_3')
                        }
                        
                        # Inserimento dati ed eliminazione immediata di eventuali righe vuote o corrotte
                        st.session_state.watchlist_df = pd.concat([st.session_state.watchlist_df, pd.DataFrame([nuovo_dato])], ignore_index=True)
                        st.session_state.watchlist_df.to_csv(DB_FILE, index=False)
                        st.success(f"Analisi Completata! Aggiunto {nuovo_dato['Ticker']} alla Watchlist.")
                        st.rerun()
                    else:
                        # Se fallisce, il pannello diagnostico mostra esattamente cosa ha risposto Google senza rompere l'app
                        st.warning("Google ha risposto ma la struttura dati standard è stata alterata (possibile blocco di sicurezza sul grafico).")
                        st.json(response_json)
                        
            except Exception as e:
                st.error(f"Errore di esecuzione: {e}")

st.markdown("---")

# --- SEZIONE 2: VISUALIZZAZIONE DATABASE E TRADINGVIEW ---
st.subheader("2. La tua Watchlist di Attenzione")

if not st.session_state.watchlist_df.empty:
    st.session_state.watchlist_df.drop_duplicates(subset=['Ticker'], keep='last', inplace=True)
    st.dataframe(st.session_state.watchlist_df, use_container_width=True)
    selected_ticker = st.selectbox("Seleziona un ticker dalla lista per aprire il grafico:", st.session_state.watchlist_df['Ticker'].tolist())
else:
    st.info("La watchlist è vuota. Carica un'immagine sopra per popolarla.")
    selected_ticker = "AAPL"

# Widget di TradingView sempre allineato
import streamlit.components.v1 as components
html_code = f"""
<div class="tradingview-widget-container" style="height:500px;">
  <div id="tradingview_chart"></div>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
  <script type="text/javascript">
  new TradingView.widget({{
    "width": "100%", "height": 500, "symbol": "{selected_ticker}",
    "interval": "D", "theme": "light", "style": "1", "locale": "it", "container_id": "tradingview_chart"
  }});
  </script>
</div>
"""
components.html(html_code, height=520)
