"""
Controllo automatico dei livelli di prezzo salvati in watchlist.csv.
Pensato per essere eseguito da un cron esterno (GitHub Actions), NON dentro
la webapp Streamlit — Streamlit Cloud non gira in background quando nessuno
la guarda, quindi gli alert reali devono partire da qui.

Richiede due secrets (impostati come GitHub Actions Secrets, NON Streamlit
Secrets, perché questo script gira via GitHub Actions):
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID
"""

import os
import json
import pandas as pd
import yfinance as yf
import requests

CSV_PATH = "watchlist.csv"
STATE_PATH = "alert_state.json"

COLONNE_ATTESE = ["Ticker", "Livello 1", "Livello 2", "Livello 3"]

# Stessa mappa usata in app.py, per coerenza tra i due script
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
    df = df.rename(columns=ALIAS_COLONNE)

    for col in COLONNE_ATTESE:
        if col not in df.columns:
            df[col] = 0

    df = df[COLONNE_ATTESE]

    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated()]

    return df

# Distanza (in %) sotto la quale consideriamo "nella zona" del livello.
# Per operazioni di lungo termine non serve precisione al tick: una zona
# più ampia intercetta l'avvicinamento al livello, non solo il tocco esatto.
# Esempio: livello 171.36 con soglia 1% -> zona ~169.6 - 173.1
SOGLIA_TRIGGER_PCT = 2.0

# Distanza (in %) oltre la quale, se il prezzo esce dalla zona, resettiamo
# l'alert per permettere una nuova notifica se il prezzo ci ritorna.
SOGLIA_RESET_PCT = 5.0

# Crypto conosciute: ticker Yahoo Finance ha il formato BTC-USD, non BTCUSD
CRYPTO_NOTE = {"BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "BNB", "LTC"}


def mappa_ticker_yfinance(ticker: str) -> str:
    """Converte il ticker salvato in watchlist nel formato richiesto da Yahoo Finance."""
    t = ticker.strip().upper()

    # Crypto: BTCUSD -> BTC-USD
    for base in CRYPTO_NOTE:
        if t == f"{base}USD":
            return f"{base}-USD"

    # Forex: coppia di 6 lettere non-crypto -> EURUSD=X
    if len(t) == 6 and t.isalpha() and t[:3] not in CRYPTO_NOTE:
        return f"{t}=X"

    # Azioni/indici: lascia invariato (AAPL, TSLA, ecc.)
    return t


def prezzo_corrente(ticker_yf: str) -> float | None:
    try:
        info = yf.Ticker(ticker_yf)
        prezzo = info.fast_info.get("lastPrice")
        if prezzo is None:
            # fallback se fast_info non ha il dato
            hist = info.history(period="1d", interval="1m")
            if hist.empty:
                return None
            prezzo = hist["Close"].iloc[-1]
        return float(prezzo)
    except Exception as e:
        print(f"Errore prezzo per {ticker_yf}: {e}")
        return None


def invia_telegram(messaggio: str):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, data={"chat_id": chat_id, "text": messaggio})
    resp.raise_for_status()


def carica_stato() -> dict:
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r") as f:
            return json.load(f)
    return {}


def salva_stato(stato: dict):
    with open(STATE_PATH, "w") as f:
        json.dump(stato, f, indent=2)


def main():
    df = carica_watchlist()
    if df.empty:
        print("watchlist.csv vuoto, nessun controllo da fare.")
        return

    stato = carica_stato()

    for _, row in df.iterrows():
        ticker = str(row["Ticker"]).strip().upper()
        ticker_yf = mappa_ticker_yfinance(ticker)
        prezzo = prezzo_corrente(ticker_yf)

        if prezzo is None:
            print(f"Prezzo non disponibile per {ticker} ({ticker_yf})")
            continue

        for i in (1, 2, 3):
            livello = row.get(f"Livello {i}")
            if pd.isna(livello) or livello == 0:
                continue

            chiave = f"{ticker}_L{i}"
            distanza_pct = abs(prezzo - livello) / livello * 100
            gia_allertato = stato.get(chiave, False)

            if distanza_pct <= SOGLIA_TRIGGER_PCT and not gia_allertato:
                msg = (
                    f"🔔 {ticker}\n"
                    f"Prezzo attuale: {prezzo:.4f}\n"
                    f"Zona livello {i} raggiunta (livello: {livello:.4f}, ±{SOGLIA_TRIGGER_PCT}%)"
                )
                invia_telegram(msg)
                stato[chiave] = True
                print(f"Alert inviato: {chiave}")

            elif distanza_pct > SOGLIA_RESET_PCT and gia_allertato:
                # Il prezzo si è allontanato abbastanza: permette un futuro re-alert
                stato[chiave] = False

    salva_stato(stato)


if __name__ == "__main__":
    main()
