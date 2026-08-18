"""
Controllo automatico dei livelli di prezzo salvati in watchlist.csv (cron GitHub Actions).
CONCETTO POC = ZONA:
  - POC (auto o manuale derivato): alert se il prezzo è DENTRO la zona [poc_low, poc_high]
  - Livelli L1-3 e VWAP 1-3: alert se entro ±SOGLIA_TRIGGER_PCT (punti, non zone)
- Regime ARGO unificato con DataEngine
- Gate multi-mercato (NYSE + Euronext)
- Skip se prezzo invariato dall'ultimo alert (niente alert duplicati a mercati chiusi)
- Persistenza via API GitHub (stato, storico, prezzi)
"""

import os
import json
import time
import io
import datetime
import base64
import pandas as pd
import requests
import mplfinance as mpf
import yfinance as yf
from zoneinfo import ZoneInfo
from data_engine import zona_poc_effettiva

MAPPA_BORSA_EUROPEA = {"CPR": "CPR.MI", "RI": "RI.PA", "NESN": "NESN.SW", "AF": "AF.PA"}

def prezzo_yfinance(ticker: str) -> float | None:
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
    simbolo = MAPPA_BORSA_EUROPEA.get(ticker, ticker)
    try:
        h = yf.Ticker(simbolo).history(period=period, interval=interval)
        return h.dropna(subset=["Close"]) if not h.empty else pd.DataFrame()
    except Exception as e:
        print(f"Errore storico yfinance per {simbolo}: {e}")
        return pd.DataFrame()

def ottieni_nome_yfinance(ticker: str) -> str | None:
    simbolo = MAPPA_BORSA_EUROPEA.get(ticker, ticker)
    try:
        info = yf.Ticker(simbolo).info
        return info.get("longName") or info.get("shortName")
    except Exception:
        return None

TD_API_KEY = os.environ.get("TWELVEDATA_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")
CSV_PATH = "watchlist.csv"
STATE_PATH = "alert_state.json"
HISTORY_PATH = "alert_history.csv"
PREZZI_PATH = "prezzi_attuali.json"

COLONNE_ATTESE = [
    "Ticker",
    "Livello 1", "Nota 1", "Livello 2", "Nota 2", "Livello 3", "Nota 3",
    "VWAP 1", "Nota VWAP 1", "VWAP 2", "Nota VWAP 2", "VWAP 3", "Nota VWAP 3",
    "Screenshot", "Origine",
    "POC 1", "POC 1 Low", "POC 1 High", "Nota POC 1",
    "POC 2", "POC 2 Low", "POC 2 High", "Nota POC 2",
    "POC 3", "POC 3 Low", "POC 3 High", "Nota POC 3",
    "Auto_Indice",
]
ALIAS_COLONNE = {
    "ticker": "Ticker", "livello": "Livello 1",
    "livello_1": "Livello 1", "livello_2": "Livello 2", "livello_3": "Livello 3",
    "vwap_1": "VWAP 1", "vwap_2": "VWAP 2", "vwap_3": "VWAP 3",
    "origine": "Origine",
    "POC": "POC 1", "poc": "POC 1",
    "Nota POC": "Nota POC 1", "nota poc": "Nota POC 1",
    "auto_indice": "Auto_Indice",
}
_TEXT_COLS = {"Screenshot", "Origine", "Auto_Indice"}
_COLONNE_NUMERICHE = [
    "Livello 1", "Livello 2", "Livello 3", "VWAP 1", "VWAP 2", "VWAP 3",
    "POC 1", "POC 1 Low", "POC 1 High", "POC 2", "POC 2 Low", "POC 2 High",
    "POC 3", "POC 3 Low", "POC 3 High",
]

def _is_text_col(col: str) -> bool:
    return col.startswith("Nota") or col in _TEXT_COLS

def _read_watchlist_github() -> pd.DataFrame | None:
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return None
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{CSV_PATH}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code != 200:
            return None
        contenuto = base64.b64decode(r.json()["content"]).decode()
        return pd.read_csv(io.StringIO(contenuto))
    except Exception as e:
        print(f"Errore lettura watchlist da GitHub: {e}")
        return None

def carica_watchlist() -> pd.DataFrame:
    df = _read_watchlist_github()
    if df is None or df.empty:
        if os.path.exists(CSV_PATH):
            df = pd.read_csv(CSV_PATH)
        else:
            return pd.DataFrame(columns=COLONNE_ATTESE)
    if df.empty:
        return pd.DataFrame(columns=COLONNE_ATTESE)
    df = df.rename(columns=ALIAS_COLONNE)
    for col in COLONNE_ATTESE:
        if col not in df.columns:
            df[col] = "" if _is_text_col(col) else 0
    df = df[COLONNE_ATTESE]
    if "Origine" in df.columns:
        df["Origine"] = df["Origine"].fillna("manuale").replace("", "manuale")
    for col in COLONNE_ATTESE:
        if _is_text_col(col):
            df[col] = df[col].fillna("").astype(str).replace("nan", "")
    for col in _COLONNE_NUMERICHE:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0).astype(float)
    # Migrazione zone: POC punto senza Low/High -> zona derivata (valore POC intatto)
    for k in (1, 2, 3):
        mask = (df[f"POC {k}"] != 0) & ((df[f"POC {k} Low"] == 0) | (df[f"POC {k} High"] == 0))
        if mask.any():
            lo, hi = zip(*[zona_poc_effettiva(p, 0, 0) for p in df.loc[mask, f"POC {k}"]])
            df.loc[mask, f"POC {k} Low"] = lo
            df.loc[mask, f"POC {k} High"] = hi
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated()]
    return df

SOGLIA_TRIGGER_PCT = 2.0
COOLDOWN_GIORNI = 1
COOLDOWN_SEC = COOLDOWN_GIORNI * 24 * 3600
SOGLIA_PREZZO_INVARIATO_PCT = 0.05  # prezzo praticamente identico -> nessun nuovo alert

CRYPTO_NOTE = {"BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "BNB", "LTC"}
_ULTIME_CHIAMATE_API = []

def rispetta_rate_limit():
    ora = time.time()
    while _ULTIME_CHIAMATE_API and ora - _ULTIME_CHIAMATE_API[0] > 60:
        _ULTIME_CHIAMATE_API.pop(0)
    if len(_ULTIME_CHIAMATE_API) >= 7:
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
    if not TD_API_KEY:
        return pd.DataFrame()
    try:
        rispetta_rate_limit()
        r = requests.get("https://api.twelvedata.com/time_series",
            params={"symbol": simbolo, "interval": interval, "outputsize": outputsize, "apikey": TD_API_KEY, "order": "ASC"})
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
        df = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
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
        r = requests.get("https://api.twelvedata.com/quote", params={"symbol": simbolo, "apikey": TD_API_KEY})
        dati = r.json()
        prezzo = dati.get("close") or dati.get("price")
        return float(prezzo) if prezzo is not None else None
    except Exception as e:
        print(f"Errore prezzo per {simbolo}: {e}")
        return None

def ottieni_regime_argo() -> dict:
    """Stessa logica di DataEngine.ottieni_bussola_argo() per coerenza."""
    try:
        df = yf.download(["^GSPC", "^VIX", "^VVIX"], period="60d", interval="1d", progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            spx = df['Close']['^GSPC'].dropna()
            vix = df['Close']['^VIX'].dropna()
            vvix = df['Close']['^VVIX'].dropna()
        else:
            spx = df[('Close', '^GSPC')].dropna()
            vix = df[('Close', '^VIX')].dropna()
            vvix = df[('Close', '^VVIX')].dropna()
        common_index = spx.index.intersection(vix.index).intersection(vvix.index)
        spx = spx.loc[common_index]
        vix = vix.loc[common_index]
        vvix = vvix.loc[common_index]
        flip_line = spx.rolling(window=20, min_periods=1).mean()
        ratio = vvix / vix
        spot = float(spx.iloc[-1])
        flip = float(flip_line.iloc[-1])
        rapporto = float(ratio.iloc[-1])
        gamma_positivo = spot >= flip
        if gamma_positivo:
            if 5.0 <= rapporto <= 7.0:
                stato, bias = "CORRENTE ASCENDENTE", "LONG"
            elif rapporto < 5.0:
                stato, bias = "CALMA PIATTA", "NEUTRO"
            else:
                stato, bias = "BIVIO STRUTTURALE", "NEUTRO"
        else:
            if rapporto > 7.0:
                stato, bias = "CASCATA DIREZIONALE", "SHORT"
            elif rapporto < 5.0:
                stato, bias = "RIMBALZO ELASTICO", "LONG"
            else:
                stato, bias = "CORRENTE DISCENDENTE", "SHORT"
        return {"stato": stato, "bias": bias, "spot": spot, "flip": flip, "ratio": rapporto}
    except Exception as e:
        print(f"Errore Bussola ARGO: {e}")
        return {"stato": "N/D", "bias": "NEUTRO", "desc": "Errore dati macro"}

def tono_messaggio(bias: str, convergenza: bool) -> str:
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
    try:
        if storico.empty:
            return None
        hlines_valori, hlines_colori, hlines_stili = [], [], []
        for liv in livelli:
            if liv["valore"] and liv["valore"] != 0:
                hlines_valori.append(liv["valore"])
                hlines_colori.append(liv["colore"])
                hlines_stili.append(liv["stile"])
                # POC con zona: disegno anche i bordi dell'area (dotted)
                lo = liv.get("low", 0)
                hi = liv.get("high", 0)
                if lo and hi and hi > lo:
                    hlines_valori += [lo, hi]
                    hlines_colori += [liv["colore"], liv["colore"]]
                    hlines_stili += [":", ":"]
        stile = mpf.make_mpf_style(base_mpf_style="nightclouds",
            marketcolors=mpf.make_marketcolors(up="#26a69a", down="#ef5350", inherit=True),
            facecolor="#0e1117", edgecolor="#1e222d", figcolor="#0e1117", gridcolor="#1e222d")
        buf = io.BytesIO()
        mpf.plot(storico, type="candle", style=stile, volume=False,
            hlines=dict(hlines=hlines_valori, colors=hlines_colori, linestyle=hlines_stili, linewidths=1.2),
            savefig=dict(fname=buf, dpi=110, bbox_inches="tight"), figsize=(9, 5))
        buf.seek(0)
        return buf.read()
    except Exception as e:
        print(f"Errore generazione grafico: {e}")
        return None

def invia_telegram(messaggio: str, immagine_bytes: bytes = None):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_ids = [c.strip() for c in os.environ["TELEGRAM_CHAT_ID"].split(",") if c.strip()]
    if immagine_bytes:
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        for chat_id in chat_ids:
            try:
                resp = requests.post(url, data={"chat_id": chat_id, "caption": messaggio}, files={"photo": ("grafico.png", immagine_bytes, "image/png")})
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

def _commit_file_github(path: str, content_text: str, message: str) -> bool:
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return False
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Content-Type": "application/json"}
        r = requests.get(url, headers=headers)
        sha = r.json().get("sha") if r.status_code == 200 else None
        payload = {"message": message, "content": base64.b64encode(content_text.encode()).decode(), "branch": "main"}
        if sha:
            payload["sha"] = sha
        resp = requests.put(url, headers=headers, json=payload)
        return resp.status_code in (200, 201)
    except Exception as e:
        print(f"Errore commit {path} su GitHub: {e}")
        return False

def carica_stato() -> dict:
    if GITHUB_TOKEN and GITHUB_REPO:
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{STATE_PATH}"
            headers = {"Authorization": f"token {GITHUB_TOKEN}"}
            r = requests.get(url, headers=headers, timeout=30)
            if r.status_code == 200:
                return json.loads(base64.b64decode(r.json()["content"]).decode())
        except Exception as e:
            print(f"Errore lettura stato da GitHub: {e}")
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r") as f:
            return json.load(f)
    return {}

def salva_stato(stato: dict):
    testo = json.dumps(stato, indent=2)
    if not _commit_file_github(STATE_PATH, testo, "Aggiorna alert_state.json"):
        with open(STATE_PATH, "w") as f:
            f.write(testo)

def registra_storico(ticker: str, livelli_toccati: list, convergenza: bool, regime: str, prezzo: float):
    livelli_str = " + ".join([f"{l['tipo']} ({l['valore']:.2f})" for l in livelli_toccati])
    riga = pd.DataFrame([{
        "Data": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "Ticker": ticker, "Livelli Toccati": livelli_str,
        "Convergenza": "Sì" if convergenza else "No", "Regime": regime,
        "Prezzo al momento": round(prezzo, 4),
    }])
    storico = None
    if GITHUB_TOKEN and GITHUB_REPO:
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{HISTORY_PATH}"
            headers = {"Authorization": f"token {GITHUB_TOKEN}"}
            r = requests.get(url, headers=headers, timeout=30)
            if r.status_code == 200:
                contenuto = base64.b64decode(r.json()["content"]).decode()
                storico = pd.read_csv(io.StringIO(contenuto))
        except Exception:
            pass
    if storico is None and os.path.exists(HISTORY_PATH):
        storico = pd.read_csv(HISTORY_PATH)
    if storico is not None:
        vecchie_colonne = {"Livello", "Valore Livello", "Nota"}
        nuove_colonne = {"Livelli Toccati", "Convergenza", "Regime"}
        if vecchie_colonne.issubset(storico.columns) and not nuove_colonne.issubset(storico.columns):
            for col in nuove_colonne:
                storico[col] = ""
        storico = pd.concat([storico, riga], ignore_index=True)
    else:
        storico = riga
    testo = storico.to_csv(index=False)
    if not _commit_file_github(HISTORY_PATH, testo, "Aggiorna alert_history.csv"):
        with open(HISTORY_PATH, "w") as f:
            f.write(testo)

def salva_prezzi(prezzi: dict):
    payload = {"aggiornato_il": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "prezzi": prezzi}
    testo = json.dumps(payload, indent=2)
    if not _commit_file_github(PREZZI_PATH, testo, "Aggiorna prezzi_attuali.json"):
        with open(PREZZI_PATH, "w") as f:
            f.write(testo)


def e_mercato_chiuso() -> bool:
    """
    True se TUTTI i mercati rilevanti sono chiusi.
    - NYSE: 9:30-16:00 ET (lun-ven)
    - Euronext (Milano/Parigi): 9:00-17:30 CET (lun-ven)
    Ritorna False se almeno uno è aperto.
    """
    tz_ny = ZoneInfo("America/New_York")
    tz_eu = ZoneInfo("Europe/Rome")
    ora_ny = datetime.datetime.now(tz_ny)
    ora_eu = datetime.datetime.now(tz_eu)

    if ora_ny.weekday() >= 5 and ora_eu.weekday() >= 5:
        return True

    minuti_ny = ora_ny.hour * 60 + ora_ny.minute
    ny_aperto = (9 * 60 + 30 <= minuti_ny <= 16 * 60) and ora_ny.weekday() < 5

    minuti_eu = ora_eu.hour * 60 + ora_eu.minute
    eu_aperto = (9 * 60 <= minuti_eu <= 17 * 60 + 30) and ora_eu.weekday() < 5

    return not (ny_aperto or eu_aperto)


def main():
    if e_mercato_chiuso():
        print("⏸️ Tutti i mercati chiusi (weekend o fuori orario). Nessun alert verrà inviato.")
        return

    if TD_API_KEY:
        print(f"TWELVEDATA_API_KEY presente, lunghezza {len(TD_API_KEY)} caratteri.")
    else:
        print("TWELVEDATA_API_KEY assente o vuota — controllare il secret su GitHub.")

    df = carica_watchlist()
    if df.empty:
        print("watchlist.csv vuoto, nessun controllo da fare.")
        return

    stato = carica_stato()
    ora_attuale = time.time()
    prezzi_raccolti = {}

    regime = ottieni_regime_argo()
    bias = regime.get("bias", "NEUTRO")
    stato_regime = regime.get("stato", "N/D")
    print(f"Bussola ARGO: {stato_regime} ({bias})")

    for _, row in df.iterrows():
        ticker = str(row["Ticker"]).strip().upper()
        ticker_td = mappa_ticker_twelvedata(ticker)
        prezzo = prezzo_corrente(ticker_td)
        if prezzo is None:
            prezzo = prezzo_yfinance(ticker)
        if prezzo is None:
            print(f"Prezzo non disponibile per {ticker} ({ticker_td})")
            continue
        prezzi_raccolti[ticker] = prezzo

        # Skip prezzo invariato: se il prezzo non si è mosso dall'ultimo alert,
        # un eventuale tocco sarebbe già stato segnalato -> niente duplicati.
        chiave_prezzo = f"{ticker}_last_price"
        ultimo_prezzo = stato.get(chiave_prezzo)
        if ultimo_prezzo is not None:
            delta_pct = abs(prezzo - ultimo_prezzo) / ultimo_prezzo * 100
            if delta_pct < SOGLIA_PREZZO_INVARIATO_PCT:
                print(f"{ticker}: prezzo invariato ({prezzo:.4f} vs {ultimo_prezzo:.4f}) -> skip")
                continue

        # Zone di tocco:
        # - L1-3 e VWAP 1-3: punti, soglia ±2%
        # - POC 1-3: ZONE [low, high] (auto reali o manuali derivate)
        livelli = []
        for i in (1, 2, 3):
            val = row.get(f"Livello {i}")
            nota = str(row.get(f"Nota {i}", "") or "").strip()
            if pd.notna(val) and val != 0:
                livelli.append({"tipo": f"L{i}", "valore": float(val), "nota": nota,
                                "zona": False, "low": 0.0, "high": 0.0,
                                "colore": ["#f0b90b", "#00c176", "#ff4d4d"][i-1], "stile": "-"})
        for k in (1, 2, 3):
            val = row.get(f"POC {k}")
            nota = str(row.get(f"Nota POC {k}", "") or "").strip()
            if pd.notna(val) and val != 0:
                lo, hi = zona_poc_effettiva(val, row.get(f"POC {k} Low"), row.get(f"POC {k} High"))
                livelli.append({"tipo": f"POC{k}", "valore": float(val), "nota": nota,
                                "zona": True, "low": lo, "high": hi,
                                "colore": "#a78bfa", "stile": "--"})
        for i in (1, 2, 3):
            val = row.get(f"VWAP {i}")
            nota = str(row.get(f"Nota VWAP {i}", "") or "").strip()
            if pd.notna(val) and val != 0:
                livelli.append({"tipo": f"VWAP {i}", "valore": float(val), "nota": nota,
                                "zona": False, "low": 0.0, "high": 0.0,
                                "colore": "#00b4d8", "stile": "--"})

        if not livelli:
            continue

        livelli_toccati = []
        in_zona_poc = False
        for liv in livelli:
            if liv["zona"]:
                # POC = zona: tocco se il prezzo è DENTRO l'area
                if liv["low"] <= prezzo <= liv["high"]:
                    livelli_toccati.append(liv)
                    in_zona_poc = True
            else:
                distanza_pct = abs(prezzo - liv["valore"]) / liv["valore"] * 100
                if distanza_pct <= SOGLIA_TRIGGER_PCT:
                    livelli_toccati.append(liv)

        chiave = f"{ticker}_touch"
        ultimo_invio = stato.get(chiave)

        if livelli_toccati:
            in_cooldown = (ultimo_invio is not None) and (ora_attuale - ultimo_invio < COOLDOWN_SEC)
            if in_cooldown:
                giorni_mancanti = (COOLDOWN_SEC - (ora_attuale - ultimo_invio)) / 86400
                print(f"{chiave} in zona ma in cooldown ({giorni_mancanti:.1f}g rimanenti) -> skip")
                continue

            nome_azienda = ottieni_nome_yfinance(ticker) or ticker
            convergenza = len(livelli_toccati) >= 2
            tono = tono_messaggio(bias, convergenza)
            storico = ottieni_time_series(ticker_td, "1day", 200)
            if storico.empty:
                storico = storico_yfinance(ticker, "6mo", "1d")
            livello_rif = min(livelli_toccati, key=lambda l: abs(prezzo - l["valore"]))
            valutazione = valuta_forza(storico, prezzo, livello_rif["valore"]) if not storico.empty else "Momentum non disponibile"
            tocchi_str = " + ".join([f"{l['tipo']} ({l['valore']:.2f})" for l in livelli_toccati])
            note_str = " | ".join([f"{l['tipo']}: {l['nota']}" for l in livelli_toccati if l["nota"]])

            msg = (f"🔔 {ticker} · {nome_azienda}\n{tono}\nPrezzo attuale: {prezzo:.4f}\n🎯 Tocco: {tocchi_str}\n")
            if in_zona_poc:
                zone_str = " + ".join([f"{l['tipo']} [{l['low']:.2f}–{l['high']:.2f}]" for l in livelli_toccati if l["zona"]])
                msg += f"📍 Prezzo dentro la zona POC: {zone_str}\n"
            if convergenza:
                msg += f"📊 Convergenza: {len(livelli_toccati)} livelli ({tocchi_str})\n"
            msg += f"🌍 Regime: {stato_regime} ({bias})\n{valutazione}\n"
            if note_str:
                msg += f"📝 Note: {note_str}\n"
            msg += f"⏳ Silenzio su {ticker} per {COOLDOWN_GIORNI} giorni (cooldown)\n"
            grafico = genera_grafico(storico, livelli)
            invia_telegram(msg, grafico)
            registra_storico(ticker, livelli_toccati, convergenza, f"{stato_regime} ({bias})", prezzo)
            stato[chiave] = ora_attuale
            stato[chiave_prezzo] = prezzo
            print(f"Alert inviato: {chiave} ({tocchi_str})")

    salva_stato(stato)
    salva_prezzi(prezzi_raccolti)
    print("✅ Check completato.")


if __name__ == "__main__":
    main()
