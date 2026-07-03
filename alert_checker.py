"""
Controllo automatico dei livelli di prezzo salvati in watchlist.csv.
Pensato per essere eseguito da un cron esterno (GitHub Actions), NON dentro
la webapp Streamlit — Streamlit Cloud non gira in background quando nessuno
la guarda, quindi gli alert reali devono partire da qui.

Richiede due secrets (impostati come GitHub Actions Secrets, NON Streamlit
Secrets, perché questo script gira via GitHub Actions):
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID   -> uno o più chat_id separati da virgola, es: "111,222"
"""

import os
import json
import time
import datetime
import pandas as pd
import yfinance as yf
import requests

CSV_PATH = "watchlist.csv"
STATE_PATH = "alert_state.json"
HISTORY_PATH = "alert_history.csv"

COLONNE_ATTESE = ["Ticker", "Livello 1", "Nota 1", "Livello 2", "Nota 2", "Livello 3", "Nota 3"]

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
            df[col] = "" if col.startswith("Nota") else 0

    df = df[COLONNE_ATTESE]

    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated()]

    return df


# Distanza (in %) sotto la quale consideriamo "nella zona" del livello.
SOGLIA_TRIGGER_PCT = 2.0

# Distanza (in %) oltre la quale, se il prezzo esce dalla zona, resettiamo l'alert.
SOGLIA_RESET_PCT = 5.0

# Se il prezzo resta nella zona più a lungo di questo, rimandiamo un promemoria.
RIALERT_ORE = 4

CRYPTO_NOTE = {"BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "BNB", "LTC"}


def mappa_ticker_yfinance(ticker: str) -> str:
    t = ticker.strip().upper()
    for base in CRYPTO_NOTE:
        if t == f"{base}USD":
            return f"{base}-USD"
    if len(t) == 6 and t.isalpha() and t[:3] not in CRYPTO_NOTE:
        return f"{t}=X"
    return t


def prezzo_corrente(ticker_yf: str) -> float | None:
    try:
        info = yf.Ticker(ticker_yf)
        prezzo = info.fast_info.get("lastPrice")
        if prezzo is None:
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
    chat_ids = [c.strip() for c in os.environ["TELEGRAM_CHAT_ID"].split(",") if c.strip()]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for chat_id in chat_ids:
        try:
            resp = requests.post(url, data={"chat_id": chat_id, "text": messaggio})
            resp.raise_for_status()
        except Exception as e:
            print(f"Invio fallito per chat_id {chat_id}: {e}")


def carica_stato() -> dict:
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r") as f:
            return json.load(f)
    return {}


def salva_stato(stato: dict):
    with open(STATE_PATH, "w") as f:
        json.dump(stato, f, indent=2)


def registra_storico(ticker: str, livello_n: int, livello_val: float, nota: str, prezzo: float):
    """Aggiunge una riga allo storico alert (alert_history.csv), creandolo se manca."""
    riga = pd.DataFrame([{
        "Data": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "Ticker": ticker,
        "Livello": livello_n,
        "Valore Livello": livello_val,
        "Nota": nota,
        "Prezzo al momento": round(prezzo, 4),
    }])

    if os.path.exists(HISTORY_PATH):
        storico = pd.read_csv(HISTORY_PATH)
        storico = pd.concat([storico, riga], ignore_index=True)
    else:
        storico = riga

    storico.to_csv(HISTORY_PATH, index=False)


def main():
    df = carica_watchlist()
    if df.empty:
        print("watchlist.csv vuoto, nessun controllo da fare.")
        return

    stato = carica_stato()
    ora_attuale = time.time()

    for _, row in df.iterrows():
        ticker = str(row["Ticker"]).strip().upper()
        ticker_yf = mappa_ticker_yfinance(ticker)
        prezzo = prezzo_corrente(ticker_yf)

        if prezzo is None:
            print(f"Prezzo non disponibile per {ticker} ({ticker_yf})")
            continue

        for i in (1, 2, 3):
            livello = row.get(f"Livello {i}")
            nota = str(row.get(f"Nota {i}", "") or "").strip()
            if pd.isna(livello) or livello == 0:
                continue

            chiave = f"{ticker}_L{i}"
            distanza_pct = abs(prezzo - livello) / livello * 100
            ultimo_invio = stato.get(chiave)

            if isinstance(ultimo_invio, bool):
                ultimo_invio = ora_attuale if ultimo_invio else None

            dentro_zona = distanza_pct <= SOGLIA_TRIGGER_PCT
            fuori_reset = distanza_pct > SOGLIA_RESET_PCT

            if dentro_zona and (
                ultimo_invio is None or (ora_attuale - ultimo_invio) >= RIALERT_ORE * 3600
            ):
                nota_riga = f"\n📝 {nota}" if nota else ""
                msg = (
                    f"🔔 {ticker}\n"
                    f"Prezzo attuale: {prezzo:.4f}\n"
                    f"Zona livello {i} raggiunta (livello: {livello:.4f}, ±{SOGLIA_TRIGGER_PCT}%)"
                    f"{nota_riga}"
                )
                invia_telegram(msg)
                registra_storico(ticker, i, livello, nota, prezzo)
                stato[chiave] = ora_attuale
                print(f"Alert inviato: {chiave}")

            elif fuori_reset and ultimo_invio is not None:
                del stato[chiave]

    salva_stato(stato)


if __name__ == "__main__":
    main()
