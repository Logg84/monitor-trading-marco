import streamlit as st
import pandas as pd
from google import genai
from PIL import Image
import json
import os

st.set_page_config(page_title="Monitor Trading", layout="wide")
st.title("Monitoraggio Asset - Ufficio Logistica")

# Configurazione del client Gemini usando il nuovo SDK ufficiale
try:
    # Il nuovo SDK legge automaticamente la variabile d'ambiente o la configuriamo così:
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
except Exception as e:
    st.error(f"Errore di configurazione Chiave API: {e}")

# Nome del file database persistente
DB_FILE = "watchlist.csv"

# Caricamento iniziale del database
if os.path.exists(DB_FILE):
    try:
        st.session_state.watchlist_df = pd.read_csv(DB_FILE)
    except:
        st.session_state.watchlist_df = pd.DataFrame(columns=["Ticker", "Livello 1", "Livello 2", "Livello 3"])
else:
    st.session_state.watchlist_df = pd.DataFrame(columns=["Ticker", "Livello 1", "Livello 2", "Livello 3"])

# --- SEZIONE 1: CARICAMENTO E ANALISI AUTOMATICA ---
st.subheader("1. Carica Grafico per Analisi Automatica con Gemini")

uploaded_file = st.file_uploader("Trascina qui lo screenshot del grafico", type=['png', 'jpg', 'jpeg', 'webp'])

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    st.image(image, caption='Grafico caricato', use_container_width=False, width=400)
    
    with st.form(key='analisi_form'):
        st.write("Clicca sul bottone qui sotto per avviare l'analisi visiva dei livelli.")
        submit_button = st.form_submit_button(label='Analizza Grafico con Gemini')
        
    if submit_button:
        with st.spinner("Gemini sta analizzando il grafico..."):
            try:
                prompt = """
                Analizza questa immagine di un grafico finanziario. 
                Trova il Ticker (es. AAPL, EURUSD, TSLA, BTCUSD) e identifica fino a 3 livelli di prezzo o di attenzione principali indicati visivamente sul grafico.
                Rispondi ESCLUSIVAMENTE con un oggetto JSON valido con questa struttura, senza testo prima o dopo:
                {
                    "ticker": "NOME_TICKER",
                    "livello_1": 123.45,
                    "livello_2": 126.80,
                    "livello_3": 130.00
                }
                Se ci sono meno di 3 livelli, imposta a null quelli mancanti. I numeri devono essere puri (senza simboli di valuta).
                """
                
                # Nuova sintassi del Client ufficiale di Google
                response = client.models.generate_content(
                    model='gemini-1.5-flash',
                    contents=[image, prompt]
                )
                
                text_response = response.text.strip()
                
                if "{" in text_response and "}" in text_response:
                    start_idx = text_response.find("{")
                    end_idx = text_response.rfind("}") + 1
                    clean_text = text_response[start_idx:end_idx]
                else:
                    clean_text = text_response
                
                data = json.loads(clean_text)
                
                nuovo_dato = {
                    "Ticker": str(data['ticker']).upper().strip(),
                    "Livello 1": data.get('livello_1'),
                    "Livello 2": data.get('livello_2'),
                    "Livello 3": data.get('livello_3')
                }
                
                st.session_state.watchlist_df = pd.concat([st.session_state.watchlist_df, pd.DataFrame([nuovo_dato])], ignore_index=True)
                st.session_state.watchlist_df.to_csv(DB_FILE, index=False)
                st.success(f"Analisi Completata! Aggiunto {nuovo_dato['Ticker']} alla Watchlist.")
                st.rerun()
            
            except Exception as e:
                st.error(f"Errore durante l'analisi: {e}")

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
    "width": "100%",
    "height": 500,
    "symbol": "{selected_ticker}",
    "interval": "D",
    "theme": "light",
    "style": "1",
    "locale": "it",
    "container_id": "tradingview_chart"
  }});
  </script>
</div>
"""
components.html(html_code, height=520)
