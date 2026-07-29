"""
Controllo automatico dei livelli di prezzo salvati in watchlist.csv.
Pensato per essere eseguito da un cron esterno (GitHub Actions), NON dentro
la webapp Streamlit — Streamlit Cloud non gira in background quando nessuno
la guarda, quindi gli alert reali devono partire da qui.

Richiede questi secrets (impostati come GitHub Actions Secrets, NON Streamlit
Secrets, perché questo script gira via GitHub Actions):
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID     -> uno o più chat_id separati da virgola, es: "111,222"
  TWELVEDATA_API_KEY
"""

import os
import json
import time
import io
import datetime
import pandas as pd
import requests
import mplfinance as mpf
import yfinance as yf

# Ticker europei che Twelve Data non copre sul piano gratuito: qui mappiamo
# il simbolo Yahoo Finance corretto (con suffisso di borsa). yfinance richiede
# il suffisso per i titoli non-USA — aggiungere qui quando se ne scopre uno nuovo.
MAPPA_BORSA_EUROPEA = {
    "CPR": "CPR.MI",    # Campari, Borsa Italiana
    "RI": "RI.PA",      # Pernod Ricard, Euronext Paris
    "NESN": "NESN.SW",  # Nestlé, SIX Swiss Exchange
    "AF": "AF.PA",      # Air France-KLM, Euronext Paris
}


def prezzo_yfinance(ticker: str) -> float | None:
    """Fallback su yfinance quando Twelve Data non copre il titolo (piano gratuito)."""
    simbolo = MAPPA_BORSA_EUROPEA.get(ticker, ticker)
    try:
        info = yf.Ticker(simbolo)
        prezzo = info.fast_info.get("lastPrice")
        if prezzo is None:
            hist = info.history(period="5d", interval="1d")
            if hist.empty:
                return None
            prezzo = hist["Close"].dropna().iloc[-1]
        return float(prezzo)
    except Exception as e:
        print(f"Errore yfinance per {simbolo}: {e}")
        return None


def storico_yfinance(ticker: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    """Fallback su yfinance per lo storico (momentum/grafico) quando Twelve Data non copre il titolo."""
    simbolo = MAPPA_BORSA_EUROPEA.get(ticker, ticker)
    try:
        h = yf.Ticker(simbolo).history(period=period, interval=interval)
        return h.dropna(subset=["Close"]) if not h.empty else pd.DataFrame()
    except Exception as e:
        print(f"Errore storico yfinance per {simbolo}: {e}")
        return pd.DataFrame()

TD_API_KEY = os.environ.get("TWELVEDATA_API_KEY")

CSV_PATH = "watchlist.csv"
STATE_PATH = "alert_state.json"
HISTORY_PATH = "alert_history.csv"

# COLONNE_ATTESE allineato a app.py + Origine + POC + Nota POC
COLONNE_ATTESE = [
    "Ticker",
    "Livello 1", "Nota 1", "Livello 2", "Nota 2", "Livello 3", "Nota 3",
    "VWAP 1", "Nota VWAP 1", "VWAP 2", "Nota VWAP 2", "VWAP 3", "Nota VWAP 3",
    "Screenshot",
    "Origine",       # manuale | auto (default manuale per proteggere i titoli esistenti)
    "POC",           # POC operativo portato dallo screener (colonna separata dai livelli manuali)
    "Nota POC",
]

# Stessa mappa usata in app.py, per coerenza tra i due script + nuove colonne
ALIAS_COLONNE = {
    "ticker": "Ticker",
    "livello": "Livello 1",
    "livello_1": "Livello 1", "livello_2": "Livello 2", "livello_3": "Livello 3",
    "vwap_1": "VWAP 1", "vwap_2": "VWAP 2", "vwap_3": "VWAP 3",
    "origine": "Origine",
    "poc": "POC",
}


def carica_watchlist() -> pd.DataFrame:
    if not os.path.exists(CSV_PATH):
        return pd.DataFrame(columns=COLONNE_ATTESE)

    df = pd.read_csv(CSV_PATH)
    df = df.rename(columns=ALIAS_COLONNE)

    for col in COLONNE_ATTESE:
        if col not in df.columns:
            df[col] = "" if (col.startswith("Nota") or col in ("Screenshot", "Origine")) else 0

    df = df[COLONNE_ATTESE]

    # Default Origine = manuale per le righe esistenti (protegge i titoli manuali)
    if "Origine" in df.columns:
        df["Origine"] = df["Origine"].fillna("manuale").replace("", "manuale")

    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated()]

    return df


# Distanza (in %) sotto la quale consideriamo "nella zona" del livello.
SOGLIA_TRIGGER_PCT = 2.0

# Distanza (in %) oltre la quale, se il prezzo esce dalla zona, resettiamo l'alert.
SOGLIA_RESET_PCT = 6.0


CRYPTO_NOTE = {"BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "BNB", "LTC"}

# Rate limiter per il piano gratuito Twelve Data (max 8 richieste/minuto).
# Con molti ticker in un solo run, rallentiamo invece di fallire.
_ULTIME_CHIAMATE_API = []


def rispetta_rate_limit():
    ora = time.time()
    while _ULTIME_CHIAMATE_API and ora - _ULTIME_CHIAMATE_API[0] > 60:
        _ULTIME_CHIAMATE_API.pop(0)
    if len(_ULTIME_CHIAMATE_API) >= 7:  # margine di sicurezza sotto il limite di 8
        attesa = 60 - (ora - _ULTIME_CHIAMATE_API[0]) + 1
        if attesa > 0:
            print(f"Rate limit Twelve Data: aspetto {attesa:.0f}s prima di continuare...")
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


def ottieni_time_series(simbolo: str, interval: str = "1day", outputsize: int = 200) -> pd.DataFrame:
    """Scarica candele OHLCV da Twelve Data, ordine cronologico crescente."""
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
            print(f"Twelve Data errore per {simbolo}: {dati.get('message', dati)}")
            return pd.DataFrame()

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
        print(f"Errore Twelve Data per {simbolo}: {e}")
        return pd.DataFrame()


def calcola_rsi(chiusure: pd.Series, periodo: int = 14) -> float | None:
    if len(chiusure) < periodo + 1:
        return None
    delta = chiusure.diff()
    guadagni = delta.clip(lower=0)
    perdite = -delta.clip(upper=0)
    media_guadagni = guadagni.rolling(periodo).mean()
    media_perdite = perdite.rolling(periodo).mean()
    ultimo_g, ultimo_p = media_guadagni.iloc[-1], media_perdite.iloc[-1]
    if ultimo_p == 0:
        return 100.0
    rs = ultimo_g / ultimo_p
    return 100 - (100 / (1 + rs))


def valuta_forza(storico: pd.DataFrame, prezzo: float, livello: float) -> str:
    """Confronta il breakout (sopra o sotto il livello) con RSI e volume,
    per capire se è sostenuto da forza reale o è probabile un fake out."""
    chiusure = storico["Close"]
    rsi = calcola_rsi(chiusure)

    vol_rel = None
    if "Volume" in storico.columns and len(storico) > 20:
        vol_medio = storico["Volume"].iloc[-21:-1].mean()
        if vol_medio > 0:
            vol_rel = (storico["Volume"].iloc[-1] / vol_medio) * 100

    if rsi is None:
        return "Momentum non disponibile"

    sopra_livello = prezzo >= livello
    vol_txt = f" (vol {vol_rel:.0f}% media)" if vol_rel is not None else ""

    if sopra_livello:
        if rsi >= 55:
            return f"💪 Forza reale (RSI {rsi:.0f}){vol_txt}"
        elif rsi < 45:
            return f"⚠️ Possibile fake out (RSI {rsi:.0f} debole){vol_txt}"
        else:
            return f"🔸 Segnale incerto (RSI {rsi:.0f}){vol_txt}"
    else:
        if rsi <= 45:
            return f"💪 Forza reale al ribasso (RSI {rsi:.0f}){vol_txt}"
        elif rsi > 55:
            return f"⚠️ Possibile fake out al ribasso (RSI {rsi:.0f} in ripresa){vol_txt}"
        else:
            return f"🔸 Segnale incerto (RSI {rsi:.0f}){vol_txt}"


def prezzo_corrente(simbolo: str) -> float | None:
    if not TD_API_KEY:
        return None
    try:
        rispetta_rate_limit()
        r = requests.get(
            "https://api.twelvedata.com/quote",
            params={"symbol": simbolo, "apikey": TD_API_KEY},
        )
        dati = r.json()
        prezzo = dati.get("close") or dati.get("price")
        return float(prezzo) if prezzo is not None else None
    except Exception as e:
        print(f"Errore prezzo per {simbolo}: {e}")
        return None


def ottieni_regime_argo() -> dict:
    """Scarica ^GSPC/^VIX/^VVIX e calcola il bias della Bussola ARGO (LONG/NEUTRO/SHORT).
    Replico la logica del motore (ottieni_bussola_argo) senza importare data_engine,
    per mantenere alert_checker.py autonomo e leggero."""
    try:
        df = yf.download(["^GSPC", "^VIX", "^VVIX"], period="60d", interval="1d", progress=False)
        if df.empty:
            return {"stato": "N/D", "bias": "NEUTRO", "desc": "Dati macro non disponibili"}
        spx = df['Close']['^GSPC'].dropna()
        vix = df['Close']['^VIX'].dropna()
        vvix = df['Close']['^VVIX'].dropna()
        common = spx.index.intersection(vix.index).intersection(vvix.index)
        spx, vix, vvix = spx.loc[common], vix.loc[common], vvix.loc[common]
        flip = spx.rolling(20, min_periods=1).mean().iloc[-1]
        spot = spx.iloc[-1]
        ratio = (vvix / vix).iloc[-1]
        gamma_positivo = spot >= flip
        if gamma_positivo:
            if 5.0 <= ratio <= 7.0:
                stato, bias = "CORRENTE ASCENDENTE", "LONG"
            elif ratio < 5.0:
                stato, bias = "CALMA PIATTA", "NEUTRO"
            else:
                stato, bias = "BIVIO STRUTTURALE", "NEUTRO"
        else:
            if ratio > 7.0:
                stato, bias = "CASCATA DIREZIONALE", "SHORT"
            elif ratio < 5.0:
                stato, bias = "RIMBALZO ELASTICO", "LONG"
            else:
                stato, bias = "CORRENTE DISCENDENTE", "SHORT"
        return {"stato": stato, "bias": bias, "spot": float(spot), "flip": float(flip), "ratio": float(ratio)}
    except Exception as e:
        print(f"Errore Bussola ARGO: {e}")
        return {"stato": "N/D", "bias": "NEUTRO", "desc": "Errore dati macro"}


def tono_messaggio(bias: str, convergenza: bool) -> str:
    """Determina il tono (verbo) del messaggio in base al regime e alla convergenza."""
    if convergenza:
        if bias == "LONG":
            return "🔥 Cluster di livelli — zona di accumulo forte"
        elif bias == "SHORT":
            return "⚡ Cluster di livelli — supporto in prova, osserva"
        else:
            return "⚡ Cluster di livelli — zona di interesse (regime neutro)"
    else:
        if bias == "LONG":
            return "📌 Zona di interesse raggiunta"
        elif bias == "SHORT":
            return "⚠️ Zona di interesse in prova (contro-trend)"
        else:
            return "📌 Zona di interesse raggiunta (regime neutro)"


def genera_grafico(storico: pd.DataFrame, livelli: list) -> bytes | None:
    """Candele + linee dei livelli (L1-3, POC, VWAP 1-3). Ritorna PNG in bytes, o None se fallisce.
    livelli: lista di dict {"valore": float, "colore": str, "stile": str, "label": str}"""
    try:
        if storico.empty:
            return None

        hlines_valori, hlines_colori, hlines_stili = [], [], []
        for liv in livelli:
            if liv["valore"] and liv["valore"] != 0:
                hlines_valori.append(liv["valore"])
                hlines_colori.append(liv["colore"])
                hlines_stili.append(liv["stile"])

        stile = mpf.make_mpf_style(
            base_mpf_style="nightclouds",
            marketcolors=mpf.make_marketcolors(up="#26a69a", down="#ef5350", inherit=True),
            facecolor="#0e1117", edgecolor="#1e222d", figcolor="#0e1117",
            gridcolor="#1e222d",
        )

        buf = io.BytesIO()
        mpf.plot(
            storico, type="candle", style=stile, volume=False,
            hlines=dict(hlines=hlines_valori, colors=hlines_colori, linestyle=hlines_stili, linewidths=1.2),
            savefig=dict(fname=buf, dpi=110, bbox_inches="tight"),
            figsize=(9, 5),
        )
        buf.seek(0)
        return buf.read()
    except Exception as e:
        print(f"Errore generazione grafico: {e}")
        return None


def invia_telegram(messaggio: str, immagine_bytes: bytes = None):
    """Manda testo (o foto+caption se c'è un'immagine) a tutti i chat_id configurati."""
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_ids = [c.strip() for c in os.environ["TELEGRAM_CHAT_ID"].split(",") if c.strip()]

    if immagine_bytes:
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        for chat_id in chat_ids:
            try:
                resp = requests.post(
                    url,
                    data={"chat_id": chat_id, "caption": messaggio},
                    files={"photo": ("grafico.png", immagine_bytes, "image/png")},
                )
                resp.raise_for_status()
            except Exception as e:
                print(f"Invio foto fallito per chat_id {chat_id}: {e}")
    else:
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


def registra_storico(ticker: str, livelli_toccati: list, convergenza: bool, regime: str, prezzo: float):
    """Aggiunge una riga allo storico alert (alert_history.csv), creandolo se manca.
    Nuovo schema: Data, Ticker, Livelli Toccati, Convergenza, Regime, Prezzo al momento."""
    livelli_str = " + ".join([f"{l['tipo']} ({l['valore']:.2f})" for l in livelli_toccati])
    riga = pd.DataFrame([{
        "Data": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "Ticker": ticker,
        "Livelli Toccati": livelli_str,
        "Convergenza": "Sì" if convergenza else "No",
        "Regime": regime,
        "Prezzo al momento": round(prezzo, 4),
    }])

    if os.path.exists(HISTORY_PATH):
        storico = pd.read_csv(HISTORY_PATH)
        # Gestisco sia il vecchio schema (Livello, Valore Livello, Nota) che il nuovo
        vecchie_colonne = {"Livello", "Valore Livello", "Nota"}
        nuove_colonne = {"Livelli Toccati", "Convergenza", "Regime"}
        if vecchie_colonne.issubset(storico.columns) and not nuove_colonne.issubset(storico.columns):
            # Migrazione: aggiungo le nuove colonne vuote
            for col in nuove_colonne:
                storico[col] = ""
        storico = pd.concat([storico, riga], ignore_index=True)
    else:
        storico = riga

    storico.to_csv(HISTORY_PATH, index=False)


PREZZI_PATH = "prezzi_attuali.json"


def salva_prezzi(prezzi: dict):
    """Salva i prezzi appena scaricati per ogni ticker, così il portale li legge
    senza doverli richiedere di nuovo lui stesso — sempre aggiornati a quando
    gira l'ultimo controllo alert (ogni ora), indipendentemente da quando si apre la pagina."""
    payload = {
        "aggiornato_il": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "prezzi": prezzi,
    }
    with open(PREZZI_PATH, "w") as f:
        json.dump(payload, f, indent=2)


def main():
    chiavi_simili = [k for k in os.environ if "TWELVE" in k.upper()]
    print(f"Variabili d'ambiente con 'TWELVE' nel nome: {chiavi_simili}")
    if TD_API_KEY:
        print(f"TWELVEDATA_API_KEY presente, lunghezza {len(TD_API_KEY)} caratteri, inizia con '{TD_API_KEY[:4]}...'")
    else:
        print("TWELVEDATA_API_KEY assente o vuota — controllare il secret su GitHub.")

    df = carica_watchlist()
    if df.empty:
        print("watchlist.csv vuoto, nessun controllo da fare.")
        return

    stato = carica_stato()
    ora_attuale = time.time()
    prezzi_raccolti = {}

    # Scarico il regime ARGO una volta per tutto il run (non per ogni ticker)
    regime = ottieni_regime_argo()
    bias = regime.get("bias", "NEUTRO")
    stato_regime = regime.get("stato", "N/D")
    print(f"Bussola ARGO: {stato_regime} ({bias})")

    for _, row in df.iterrows():
        ticker = str(row["Ticker"]).strip().upper()
        ticker_td = mappa_ticker_twelvedata(ticker)
        prezzo = prezzo_corrente(ticker_td)
        fonte = "Twelve Data"

        if prezzo is None:
            prezzo = prezzo_yfinance(ticker)
            fonte = "yfinance (fallback)"

        if prezzo is None:
            print(f"Prezzo non disponibile per {ticker} ({ticker_td})")
            continue

        prezzi_raccolti[ticker] = prezzo

        # Raccolgo tutti i livelli presenti: L1-3, POC, VWAP 1-3
        livelli = []
        for i in (1, 2, 3):
            val = row.get(f"Livello {i}")
            nota = str(row.get(f"Nota {i}", "") or "").strip()
            if pd.notna(val) and val != 0:
                livelli.append({"tipo": f"L{i}", "valore": float(val), "nota": nota, "colore": ["#f0b90b", "#00c176", "#ff4d4d"][i-1], "stile": "-"})
        poc_val = row.get("POC")
        poc_nota = str(row.get("Nota POC", "") or "").strip()
        if pd.notna(poc_val) and poc_val != 0:
            livelli.append({"tipo": "POC", "valore": float(poc_val), "nota": poc_nota, "colore": "#ff4d4d", "stile": "--"})
        for i in (1, 2, 3):
            val = row.get(f"VWAP {i}")
            nota = str(row.get(f"Nota VWAP {i}", "") or "").strip()
            if pd.notna(val) and val != 0:
                livelli.append({"tipo": f"VWAP {i}", "valore": float(val), "nota": nota, "colore": "#00b4d8", "stile": "--"})

        if not livelli:
            continue

        # Calcolo distanza % per ogni livello e trovo quelli toccati
        livelli_toccati = []
        for liv in livelli:
            distanza_pct = abs(prezzo - liv["valore"]) / liv["valore"] * 100
            if distanza_pct <= SOGLIA_TRIGGER_PCT:
                livelli_toccati.append(liv)

        chiave = f"{ticker}_touch"  # Nuova chiave: un unico stato per ticker (non per livello)
        ultimo_invio = stato.get(chiave)

        if isinstance(ultimo_invio, bool):
            ultimo_invio = ora_attuale if ultimo_invio else None

        if livelli_toccati and ultimo_invio is None:
            # Almeno un livello toccato e alert non ancora inviato
            convergenza = len(livelli_toccati) >= 2
            tono = tono_messaggio(bias, convergenza)

            # Storico per il grafico e la valutazione forza
            storico = ottieni_time_series(ticker_td, "1day", 200)
            if storico.empty:
                storico = storico_yfinance(ticker, "6mo", "1d")
            # Valutazione forza sul primo livello toccato (o il più vicino)
            livello_rif = min(livelli_toccati, key=lambda l: abs(prezzo - l["valore"]))
            valutazione = valuta_forza(storico, prezzo, livello_rif["valore"]) if not storico.empty else "Momentum non disponibile"

            # Compongo il messaggio con la tassonomia dei tocchi
            tocchi_str = " + ".join([f"{l['tipo']} ({l['valore']:.2f})" for l in livelli_toccati])
            note_str = " | ".join([f"{l['tipo']}: {l['nota']}" for l in livelli_toccati if l["nota"]])

            msg = (
                f"🔔 {ticker}\n"
                f"{tono}\n"
                f"Prezzo attuale: {prezzo:.4f}\n"
                f"🎯 Tocco: {tocchi_str}\n"
            )
            if convergenza:
                msg += f"📊 Convergenza: {len(livelli_toccati)} livelli ({tocchi_str})\n"
            msg += f"🌍 Regime: {stato_regime} ({bias})\n"
            msg += f"{valutazione}\n"
            if note_str:
                msg += f"📝 Note: {note_str}\n"

            # Grafico con tutti i livelli (L1-3, POC, VWAP 1-3)
            grafico = genera_grafico(storico, livelli)
            invia_telegram(msg, grafico)
            registra_storico(ticker, livelli_toccati, convergenza, f"{stato_regime} ({bias})", prezzo)
            stato[chiave] = ora_attuale
            print(f"Alert inviato: {chiave} ({tocchi_str})")

        elif not livelli_toccati and ultimo_invio is not None:
            # Verifico se il prezzo è uscito da TUTTI i livelli (distanza > SOGLIA_RESET_PCT)
            fuori_da_tutti = all(
                abs(prezzo - liv["valore"]) / liv["valore"] * 100 > SOGLIA_RESET_PCT
                for liv in livelli
            )
            if fuori_da_tutti:
                del stato[chiave]
                print(f"Alert resettato: {chiave} (prezzo uscito da tutti i livelli)")

    salva_stato(stato)
    salva_prezzi(prezzi_raccolti)


if __name__ == "__main__":
    main()
