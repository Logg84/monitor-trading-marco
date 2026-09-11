"""
Pagina Simulazione Trading: visualizza i trade generati automaticamente
dagli alert REVERSAL con punteggio ≥ 4/6.

Legge da: data/simulazione_trades.csv (scritto da core/simulazione_engine.py)
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path
import yfinance as yf

st.set_page_config(page_title="Simulazione Trading", page_icon="🎮", layout="wide",
                   initial_sidebar_state="collapsed")

from ui.theme import inject_css
from ui.nav import render_navbar, sidebar_nav

if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = True

inject_css(dark=st.session_state.dark_mode)
render_navbar(title="Simulazione")
sidebar_nav()

CSV_PATH = Path("data/simulazione_trades.csv")


@st.cache_data(ttl=3600)
def carica_dati() -> pd.DataFrame:
    if not CSV_PATH.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(CSV_PATH)
        if df.empty:
            return df
        df['Data_Ingresso'] = pd.to_datetime(df['Data_Ingresso'])
        if 'Data_Uscita' in df.columns:
            df['Data_Uscita'] = pd.to_datetime(df['Data_Uscita'], errors='coerce')
        return df
    except Exception as e:
        st.error(f"Errore caricamento dati simulazione: {e}")
        return pd.DataFrame()


# ── Header ────────────────────────────────────────────────────
st.markdown("## 🎮 Simulazione Trading")
st.caption(
    "Trade generati automaticamente dagli alert **REVERSAL** con punteggio **≥ 4/6**. "
    "Entry sul prezzo dell'alert · SL sull'ultimo minimo settimanale · "
    "TP1 a RR 1:1,5 (chiude 20%, SL → breakeven) · TP2 a +33% (chiude 20%) · "
    "TP3 a +50% (chiude 30%) · TP4 a +100% (chiude 30%). "
    "Il simulatore viene eseguito dal workflow GitHub Actions ogni 2 ore nei giorni di mercato."
)

df = carica_dati()

if df.empty:
    st.info(
        "📭 **Nessun trade in simulazione.**\n\n"
        "Il primo alert **REVERSAL** con punteggio **≥ 4/6** genererà automaticamente il primo trade.\n\n"
        "**Come funziona:**\n"
        "1. Il workflow `alerts.yml` esegue `alert_checker.py` → invia segnali Telegram\n"
        "2. Subito dopo, esegue `simulazione_engine.py` che:\n"
        "   - Apre un nuovo trade LONG per ogni alert REVERSAL con score ≥ 4/6\n"
        "   - Aggiorna PnL latente dei trade aperti\n"
        "   - Chiude i trade che raggiungono SL o TP\n"
        "3. I dati vengono salvati in `data/simulazione_trades.csv` e commitati su GitHub\n\n"
        "**Cosa NON apre trade:**\n"
        "- ❌ Alert CANDELONE/Sifrediana (solo contesto informativo)\n"
        "- ❌ Alert REVERSAL con score < 4/6\n"
        "- ❌ Ticker che ha già un trade aperto\n"
        "- ❌ Ticker che ha chiuso un trade negli ultimi 30 giorni\n\n"
        "**Parametri di default** (modificabili in `core/simulazione_engine.py`):\n"
        "- Stop Loss: ultimo minimo settimanale (ultime 4 settimane)\n"
        "- Take Profit 1: RR 1:1,5 (chiude 20% della posizione, SL → breakeven)\n"
        "- Take Profit 2: +33% di gain (chiude 20%)\n"
        "- Take Profit 3: +50% di gain (chiude 30%)\n"
        "- Take Profit 4: +100% di gain (chiude 30%, trade chiuso)\n"
        "- Score minimo per aprire un trade: 4/6"
    )
    st.stop()

# ── KPI ───────────────────────────────────────────────────────
trade_chiusi = df[df['Stato'] == 'Chiuso']
trade_aperti = df[df['Stato'] == 'Aperto']
tot_trade = len(df)

pnl_chiusi = trade_chiusi['PnL_Realizzato_%'].sum() if len(trade_chiusi) > 0 else 0
pnl_laten = trade_aperti['PnL_Latente_%'].sum() if len(trade_aperti) > 0 else 0
pnl_totale = pnl_chiusi + pnl_laten

if len(trade_chiusi) > 0:
    win_rate = (trade_chiusi['PnL_Realizzato_%'] > 0).sum() / len(trade_chiusi) * 100
else:
    win_rate = 0.0

if 'Max_Drawdown_%' in df.columns and len(df) > 0:
    max_dd = df['Max_Drawdown_%'].min()
else:
    max_dd = 0.0

# Profit factor
if len(trade_chiusi) > 0:
    wins = trade_chiusi[trade_chiusi['PnL_Realizzato_%'] > 0]
    losses = trade_chiusi[trade_chiusi['PnL_Realizzato_%'] <= 0]
    avg_win = wins['PnL_Realizzato_%'].mean() if len(wins) > 0 else 0
    avg_loss = abs(losses['PnL_Realizzato_%'].mean()) if len(losses) > 0 else 0.01
    profit_factor = avg_win / avg_loss if avg_loss > 0 else 0
else:
    profit_factor = 0.0

st.markdown("### 📊 Performance")
col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Trade Totali", tot_trade)
col2.metric("Aperti", len(trade_aperti))
col3.metric("PnL Realizzato", f"{pnl_chiusi:+.2f}%")
col4.metric("PnL Latente", f"{pnl_laten:+.2f}%")
col5.metric("PnL Totale", f"{pnl_totale:+.2f}%")
col6.metric("Win Rate", f"{win_rate:.1f}%")

col7, col8, col9 = st.columns(3)
col7.metric("Profit Factor", f"{profit_factor:.2f}")
col8.metric("Max Drawdown", f"{max_dd:.2f}%")
if len(trade_chiusi) > 0:
    n_wins = len(trade_chiusi[trade_chiusi['PnL_Realizzato_%'] > 0])
    n_losses = len(trade_chiusi[trade_chiusi['PnL_Realizzato_%'] <= 0])
    col9.metric("Vittorie / Sconfitte", f"{n_wins} / {n_losses}")
else:
    col9.metric("Vittorie / Sconfitte", "0 / 0")

st.divider()

# ── Trade Aperti ──────────────────────────────────────────────
st.markdown("### 🟢 Trade Aperti")
if not trade_aperti.empty:
    # Calcola prezzo corrente per ogni trade
    trade_aperti_display = trade_aperti.copy()
    prezzi_correnti = []
    
    for idx, row in trade_aperti_display.iterrows():
        ticker = row['Ticker']
        try:
            tk = yf.Ticker(ticker)
            hist = tk.history(period="1d")
            if not hist.empty:
                prezzo_corrente = float(hist['Close'].iloc[-1])
                prezzi_correnti.append(prezzo_corrente)
            else:
                prezzi_correnti.append(None)
        except Exception:
            prezzi_correnti.append(None)
    
    trade_aperti_display['Prezzo_Corrente'] = prezzi_correnti
    
    # Semplifica la colonna Note: mostra solo l'emoji del reversal
    def get_reversal_emoji(note):
        if 'REVERSAL_GREEN' in str(note):
            return '🟢'
        elif 'REVERSAL_YELLOW' in str(note):
            return '🟡'
        return '—'
    
    trade_aperti_display['Segnale'] = trade_aperti_display['Note'].apply(get_reversal_emoji)
    
    cols_to_show = ['Ticker', 'Prezzo_Ingresso', 'Prezzo_Corrente', 'SL_Attuale', 
                    'TP1_Prezzo', 'TP2_Prezzo', 'TP3_Prezzo', 'TP4_Prezzo', 
                    'Quantita_Residua_%', 'PnL_Realizzato_%', 'PnL_Latente_%', 
                    'Max_Drawdown_%', 'Score_Alert', 'Segnale']
    cols_to_show = [c for c in cols_to_show if c in trade_aperti_display.columns]
    
    st.dataframe(
        trade_aperti_display[cols_to_show].style.format({
            'Prezzo_Ingresso': '{:.2f}',
            'Prezzo_Corrente': '{:.2f}',
            'SL_Attuale': '{:.2f}',
            'TP1_Prezzo': '{:.2f}',
            'TP2_Prezzo': '{:.2f}',
            'TP3_Prezzo': '{:.2f}',
            'TP4_Prezzo': '{:.2f}',
            'Quantita_Residua_%': '{:.0f}%',
            'PnL_Realizzato_%': '{:+.2f}%',
            'PnL_Latente_%': '{:+.2f}%',
            'Max_Drawdown_%': '{:.2f}%',
        }),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("Nessun trade aperto al momento.")

# ── Trade Chiusi ──────────────────────────────────────────────
st.markdown("### 🔴 Trade Chiusi")
if not trade_chiusi.empty:
    cols_to_show = ['Data_Ingresso', 'Ticker', 'Prezzo_Ingresso', 'Prezzo_Uscita',
                    'PnL_Realizzato_%', 'Max_Drawdown_%', 'Score_Alert',
                    'Motivo_Uscita', 'Data_Uscita', 'Note']
    cols_to_show = [c for c in cols_to_show if c in trade_chiusi.columns]

    if 'Data_Uscita' in trade_chiusi.columns:
        display_df = trade_chiusi.sort_values('Data_Uscita', ascending=False)
    else:
        display_df = trade_chiusi

    st.dataframe(
        display_df[cols_to_show].style.format({
            'Prezzo_Ingresso': '{:.2f}',
            'Prezzo_Uscita': '{:.2f}',
            'PnL_Realizzato_%': '{:+.2f}%',
            'Max_Drawdown_%': '{:.2f}%',
        }),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("Nessun trade chiuso al momento.")

# ── Equity Curve ──────────────────────────────────────────────
st.markdown("### 📈 Equity Curve")
if len(df) > 0:
    df_sorted = df.sort_values('Data_Ingresso').copy()
    df_sorted['PnL_Per_Trade'] = df_sorted['PnL_Realizzato_%'].fillna(0)
    df_sorted['PnL_Cumulato'] = df_sorted['PnL_Per_Trade'].cumsum()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_sorted['Data_Ingresso'],
        y=df_sorted['PnL_Cumulato'],
        mode='lines+markers',
        name='PnL Realizzato',
        line=dict(color='#00d4ff', width=2),
        marker=dict(size=6),
        hovertemplate='Data: %{x|%Y-%m-%d}<br>PnL: %{y:.2f}%<extra></extra>'
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
    fig.update_layout(
        height=400,
        xaxis_title="Data",
        yaxis_title="PnL Cumulato %",
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        showlegend=True,
        font=dict(color='#b0b8c4'),
    )
    st.plotly_chart(fig, use_container_width=True)

    if pnl_laten != 0:
        st.caption(f"PnL latente dei trade aperti (non incluso nella curva): {pnl_laten:+.2f}%")
else:
    st.info("Dati insufficienti per generare la equity curve.")

# ── Log esecuzioni ────────────────────────────────────────────
LOG_PATH = Path("data/simulation_log.json")
if LOG_PATH.exists():
    with st.expander("📝 Log esecuzioni simulatore"):
        try:
            import json
            log = json.loads(LOG_PATH.read_text(encoding="utf-8"))
            if log:
                log_df = pd.DataFrame(reversed(log))
                st.dataframe(log_df, use_container_width=True, hide_index=True)
            else:
                st.caption("Log vuoto.")
        except Exception as e:
            st.caption(f"Errore lettura log: {e}")

# ── Spiegazione ───────────────────────────────────────────────
with st.expander("📖 Come funziona il simulatore"):
    st.markdown("""
**Logica di apertura trade:**
- Il workflow GitHub Actions (`alerts.yml`) esegue ogni 2 ore nei giorni di mercato
- Dopo `alert_checker.py`, viene eseguito `simulazione_engine.py`
- Per ogni alert **REVERSAL** (🟡 o 🟢) con score **≥ 4/6**, viene aperto un nuovo trade **LONG**
- Un ticker può avere **un solo trade aperto alla volta**
- Dopo la chiusura, il ticker non viene riaperto per 30 giorni

**Cosa NON apre trade:**
- ❌ Alert CANDELONE/Sifrediana → sono solo contesto informativo
- ❌ Alert REVERSAL con score < 4/6
- ❌ Ticker già in portafoglio (trade aperto)
- ❌ Ticker chiuso da meno di 30 giorni

**Logica di chiusura (scalata progressiva):**
- **Stop Loss**: sull'ultimo minimo settimanale (ultime 4 settimane)
- **Take Profit 1 (RR 1:1,5)**: chiude il 20% della posizione, sposta SL a breakeven
- **Take Profit 2 (+33%)**: chiude il 20% della posizione
- **Take Profit 3 (+50%)**: chiude il 30% della posizione
- **Take Profit 4 (+100%)**: chiude il restante 30%, trade chiuso

**Parametri (modificabili in `core/simulazione_engine.py`):**
```python
SL_LOOKBACK_DAYS = 28       # Minimo delle ultime 4 settimane
TP1_RR_RATIO = 1.5          # TP1 a RR 1:1,5
TP2_GAIN_PCT = 33.0         # TP2 a +33% di gain
TP3_GAIN_PCT = 50.0         # TP3 a +50% di gain
TP4_GAIN_PCT = 100.0        # TP4 a +100% di gain
TP1_CLOSE_PCT = 20.0        # TP1 chiude 20%
TP2_CLOSE_PCT = 20.0        # TP2 chiude 20%
TP3_CLOSE_PCT = 30.0        # TP3 chiude 30%
TP4_CLOSE_PCT = 30.0        # TP4 chiude 30%
MIN_SCORE_FOR_TRADE = 4     # Score minimo
```

**Nota**: questa è una simulazione didattica. Non tiene conto di slippage,
commissioni, o liquidità reale. I risultati passati non garantiscono performance future.
""")
