import streamlit as st
import pandas as pd
import streamlit.components.v1 as components

st.set_page_config(page_title="Monitor Trading", layout="wide")

st.title("Monitoraggio Asset - Ufficio Logistica")

# Legge il file CSV che abbiamo creato su GitHub
try:
    df = pd.read_csv("watchlist.csv")
    st.subheader("La tua Watchlist")
    st.table(df)
    
    # Seleziona un ticker dalla lista per vedere il grafico
    selected_ticker = st.selectbox("Seleziona ticker da visualizzare:", df['ticker'].tolist())
except:
    st.error("File watchlist.csv non trovato nel repository!")
    selected_ticker = "AAPL"

# Widget TradingView
st.subheader(f"Grafico Live: {selected_ticker}")
html_code = f"""
<div class="tradingview-widget-container">
  <div id="tradingview_chart"></div>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
  <script type="text/javascript">
  new TradingView.widget({{
    "width": "100%", "height": 500,
    "symbol": "{selected_ticker}",
    "interval": "D", "theme": "light", "locale": "it",
    "container_id": "tradingview_chart"
  }});
  </script>
</div>
"""
components.html(html_code, height=550)
