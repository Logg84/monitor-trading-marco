import streamlit as st
import streamlit.components.v1 as components

# Configurazione pagina
st.set_page_config(page_title="Monitor Trading Marco", layout="wide")

st.title("Monitoraggio Asset - Ufficio Logistica")

# Sezione Input
col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("Aggiungi Livello")
    ticker = st.text_input("Inserisci Ticker (es. AAPL, EURUSD)").upper()
    level = st.number_input("Livello di Attenzione", format="%.2f")
    if st.button("Aggiungi alla lista"):
        if 'watchlist' not in st.session_state:
            st.session_state.watchlist = []
        st.session_state.watchlist.append({"ticker": ticker, "level": level})
        st.success(f"Aggiunto {ticker} a {level}")

# Sezione Widget TradingView
with col2:
    st.subheader("Grafico Live")
    if ticker:
        # Widget TradingView ufficiale
        html_code = f"""
        <div class="tradingview-widget-container">
          <div id="tradingview_chart"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
          <script type="text/javascript">
          new TradingView.widget({{
            "width": "100%",
            "height": 500,
            "symbol": "{ticker}",
            "interval": "D",
            "timezone": "Etc/UTC",
            "theme": "light",
            "style": "1",
            "locale": "it",
            "toolbar_bg": "#f1f3f6",
            "enable_publishing": false,
            "container_id": "tradingview_chart"
          }});
          </script>
        </div>
        """
        components.html(html_code, height=550)
    else:
        st.info("Inserisci un ticker per visualizzare il grafico")

# Tabella Watchlist
st.subheader("La tua Watchlist")
if 'watchlist' in st.session_state:
    st.table(st.session_state.watchlist)
