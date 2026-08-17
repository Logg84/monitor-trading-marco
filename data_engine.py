import os
import re
import json
import time
import datetime
import traceback
import requests
import io
import pandas as pd
import numpy as np
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed

# === MANOPOLE "POC OPERATIVO" (ritoccale qui) ===
MAX_POC_DIST_PCT = 50.0     # oltre questa distanza dal prezzo, un POC è un relitto: ignorato
MIN_POC_WEIGHT_NORM = 5.0   # l'alert SU POC scatta solo se il POC vicino ha peso >= questo
POC_MERGE_PCT = 2.5         # POC della watchlist entro questa % l'uno dall'altro vengono accorpati

# === MANOPOLE ZONE POC (aree, non punti) ===
ZONE_MIN_PCT = 0.60         # bin adiacenti >= 60% del volume del POC -> zona
LVN_FLOOR_PCT = 0.15        # floor assoluto rispetto al max del profilo
USE_LVN_EDGE = True         # ferma l'estensione al LVN
MANUAL_POC_ZONE_PCT = 1.0   # semi-ampiezza % della zona derivata per POC inseriti come punto (manuali/legacy)

# === FINESTRE TEMPORALI (in barre daily = giorni di trading) ===
BARS_PER_YEAR = 252
WIN_VWAP_3M = 63
WIN_VWAP_1Y = 252
WIN_VWAP_4Y = 1008
WIN_ROC = 70
WIN_ROC_COMPARE = 15
WIN_VOL = 25
WIN_MOM = 5

# === NUMERO DI POC PORTATI IN WATCHLIST ===
N_POC_WATCHLIST = 3


def zona_poc_effettiva(poc, low, high, manual_pct=MANUAL_POC_ZONE_PCT):
    """
    Concetto unico: un POC è SEMPRE una zona.
    - se low/high presenti e validi -> la zona è quella (POC auto)
    - se il POC è un punto (manuale/legacy) -> zona derivata ±manual_pct%
    Ritorna (low, high). Se POC assente -> (0.0, 0.0).
    """
    p = float(poc or 0)
    if p <= 0:
        return 0.0, 0.0
    lo = float(low or 0)
    hi = float(high or 0)
    if lo > 0 and hi > 0:
        return lo, hi
    return round(p * (1 - manual_pct / 100.0), 4), round(p * (1 + manual_pct / 100.0), 4)


NASDAQ100_STATIC = [
    "AAPL", "ADBE", "ADI", "ADSK", "ADP", "ABNB", "ALNY", "AMAT", "AMD", "AMGN",
    "AMZN", "ANSS", "AEP", "APP", "ASML", "AVGO", "AXON", "BKR", "BIIB", "BKNG",
    "CDNS", "CEG", "CHTR", "CMCSA", "CPRT", "CRWD", "CRWV", "CSCO", "CSX", "CTAS",
    "CTSH", "DASH", "DDOG", "DLTR", "DXCM", "EA", "EXC", "FANG", "FAST", "FTNT",
    "GEHC", "GFS", "GILD", "GOOG", "GOOGL", "HON", "IDXX", "ILMN", "INSM", "INTC",
    "INTU", "ISRG", "KDP", "KHC", "KLAC", "LRCX", "LITE", "LULU", "MAR", "MCHP",
    "MDLZ", "MELI", "META", "MNST", "MRVL", "MU", "MSTR", "MPWR", "NDAQ", "NFLX",
    "NVDA", "NXPI", "ODFL", "ON", "ORLY", "PANW", "PAYX", "PDD", "PEP", "PLTR",
    "PYPL", "QCOM", "REGN", "ROP", "RKLB", "SBUX", "SHOP", "SNDK", "SNPS", "STX",
    "TMUS", "TSLA", "TXN", "TRI", "VRTX", "WBD", "WDC", "WDAY", "XEL", "ZS",
]

# === DAX 40 STATICO (riserva: integra Wikipedia se parziale) ===
DAX40_STATIC = [
    "ADS", "AIR", "ALV", "BAS", "BAYN", "BEI", "BNR", "BMW", "CBK", "CON",
    "COV", "DB1", "DBK", "DHL", "DTE", "DTG", "EOAN", "FME", "FRE", "HEI",
    "HEN3", "IFX", "LIN", "MBG", "MRK", "MUV2", "PAH3", "P911", "PUM", "QIA",
    "RHM", "RWE", "SAP", "SDF", "SHL", "SIE", "SY1", "VNA", "VW3", "ZAL",
]

_HEADER_TARGETS = [
    "ticker symbol", "symbol", "ticker", "tickersymbol",
    "company symbol", "codice", "symbole", "componenti",
]


class DataEngine:
    def __init__(self, base_dir=None, data_file="argo_database.json", state_file="screener_state.json", cache_file="fundamentals_cache.json"):
        self.base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
        self.data_path = os.path.join(self.base_dir, data_file)
        self.state_path = os.path.join(self.base_dir, state_file)
        self.cache_path = os.path.join(self.base_dir, cache_file)
        self.screener_database = {}
        self.screener_state = {}
        self.fundamentals_cache = {}
        self.debug_log = []
        self.load_all()

    def add_debug(self, msg, level="info"):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.debug_log.append({"time": timestamp, "msg": msg, "level": level})
        if len(self.debug_log) > 200:
            self.debug_log = self.debug_log[-200:]
        print(f"[{level.upper()}] {timestamp} - {msg}")

    def _norm_header(self, s):
        s = str(s)
        s = re.sub(r"\s+", " ", s).strip()
        s = re.sub(r"\[[^\]]*\]", "", s)
        s = re.sub(r"\([^)]*\)", "", s)
        s = s.lower()
        s = re.sub(r"[^a-z ]", "", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def _clean_val(self, s):
        s = str(s)
        s = s.split("[")[0]
        s = re.sub(r"\s+", "", s)
        s = s.encode("ascii", "ignore").decode()
        return s.strip().upper()

    def _is_ticker_like(self, s):
        s = self._clean_val(s)
        if not s or len(s) > 6:
            return False
        if not any(c.isalpha() for c in s):
            return False
        return all(c.isupper() or c.isdigit() or c in ".-" for c in s)

    def clean_for_json(self, obj):
        if isinstance(obj, dict):
            return {k: self.clean_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.clean_for_json(v) for v in obj]
        elif isinstance(obj, pd.DataFrame):
            return obj.to_dict(orient='records')
        elif isinstance(obj, pd.Series):
            return obj.tolist()
        elif isinstance(obj, (np.integer, np.int64)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        elif isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        else:
            return obj

    def load_all(self):
        if os.path.exists(self.data_path):
            try:
                with open(self.data_path, "r") as f:
                    self.screener_database = json.load(f)
                self.add_debug("Database screener caricato con successo.", "success")
            except Exception as e:
                self.add_debug(f"Errore caricamento database: {e}", "error")
                self.screener_database = {}
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, "r") as f:
                    self.screener_state = json.load(f)
                self.add_debug("Stato storico caricato con successo.", "success")
            except Exception as e:
                self.add_debug(f"Errore caricamento stato: {e}", "error")
                self.screener_state = {}
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r") as f:
                    self.fundamentals_cache = json.load(f)
                self.add_debug(f"Cache fondamentali caricata ({len(self.fundamentals_cache)} elementi).", "success")
            except Exception as e:
                self.add_debug(f"Errore caricamento cache fondamentali: {e}", "error")
                self.fundamentals_cache = {}

    def save_all(self):
        self.save_database()
        self.save_state()
        self.save_cache()

    def save_database(self):
        try:
            cleaned = self.clean_for_json(self.screener_database)
            with open(self.data_path, "w") as f:
                json.dump(cleaned, f, indent=4)
        except Exception as e:
            self.add_debug(f"Errore salvataggio database: {e}", "error")

    def save_state(self):
        try:
            cleaned = self.clean_for_json(self.screener_state)
            with open(self.state_path, "w") as f:
                json.dump(cleaned, f, indent=4)
        except Exception as e:
            self.add_debug(f"Errore salvataggio stato: {e}", "error")

    def save_cache(self):
        try:
            cleaned = self.clean_for_json(self.fundamentals_cache)
            with open(self.cache_path, "w") as f:
                json.dump(cleaned, f, indent=4)
        except Exception as e:
            self.add_debug(f"Errore salvataggio cache fondamentali: {e}", "error")

    def _save_to_history_cache(self, ticker, df):
        if df is None or df.empty:
            return
        try:
            cache_dir = os.path.join(self.base_dir or "", "history_cache")
            os.makedirs(cache_dir, exist_ok=True)
            cache_path = os.path.join(cache_dir, f"{ticker.upper()}.json")
            df_reset = df.copy().reset_index()
            date_col = None
            for c in ["Date", "date", "index"]:
                if c in df_reset.columns:
                    date_col = c
                    break
            if date_col:
                df_reset[date_col] = pd.to_datetime(df_reset[date_col]).dt.strftime("%Y-%m-%d")
                df_reset.rename(columns={date_col: "date"}, inplace=True)
            data = df_reset.to_dict(orient="records")
            with open(cache_path, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            self.add_debug(f"Errore salvataggio cache storica per {ticker}: {e}", "warning")

    def _load_from_history_cache(self, ticker):
        try:
            cache_dir = os.path.join(self.base_dir or "", "history_cache")
            cache_path = os.path.join(cache_dir, f"{ticker.upper()}.json")
            if os.path.exists(cache_path):
                with open(cache_path, "r") as f:
                    data = json.load(f)
                df = pd.DataFrame(data)
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"])
                    df.set_index("date", inplace=True)
                return df
        except Exception as e:
            self.add_debug(f"Errore lettura cache storica per {ticker}: {e}", "warning")
        return None

    # ===============================
    # LETTURA LISTE INDICI DA GITHUB (fonte primaria mensile)
    # ===============================
    def _read_index_from_github(self, name, suffix=""):
        repo = os.environ.get("GITHUB_REPO")
        if not repo:
            return None
        url = f"https://raw.githubusercontent.com/{repo}/main/indices/{name}.csv"
        headers = {'User-Agent': 'ARGO-DataEngine/1.0'}
        try:
            r = requests.get(url, headers=headers, timeout=20)
            if r.status_code != 200:
                self.add_debug(f"[indices] {name}: GitHub HTTP {r.status_code}", "warning")
                return None
            df = pd.read_csv(io.StringIO(r.text))
            if "ticker" not in df.columns:
                self.add_debug(f"[indices] {name}: CSV senza colonna 'ticker'", "warning")
                return None
            raw = df["ticker"].dropna().astype(str).str.strip().str.upper().tolist()
            raw = [t for t in raw if t]
            if suffix:
                tickers = [t if "." in t else t + suffix for t in raw]
            else:
                tickers = raw
            source_label = "GitHub"
            fetched_label = "?"
            if "fetched_at" in df.columns:
                fa = df["fetched_at"].iloc[0]
                if pd.notna(fa):
                    fetched_label = str(fa)[:10]
                    try:
                        dt = datetime.datetime.fromisoformat(str(fa).replace("Z", ""))
                        age_days = (datetime.datetime.now() - dt).days
                        source_label += f" ({age_days}gg fa)"
                        if age_days > 40:
                            self.add_debug(f"[indices] {name}: lista GitHub obsoleta ({age_days}gg).", "warning")
                    except Exception:
                        pass
            if "source" in df.columns:
                src = df["source"].iloc[0]
                if pd.notna(src) and str(src).strip():
                    source_label += f" via {src}"
            self.add_debug(f"[indices] {name}: {len(tickers)} ticker da {source_label} (fetched: {fetched_label})", "success")
            return tickers
        except Exception as e:
            self.add_debug(f"[indices] {name}: fallito GitHub ({e})", "warning")
            return None

    # ===============================
    # ESTRAZIONE TICKERS (multi-parser)
    # ===============================
    def estrai_ticker_wikipedia(self, url, headers=None):
        headers = headers or {'User-Agent': 'Mozilla/5.0'}
        self.add_debug(f"Estrazione ticker da: {url}", "info")
        try:
            res = requests.get(url, headers=headers, timeout=30)
            if res.status_code != 200:
                raise ConnectionError(f"Wikipedia ha risposto con codice {res.status_code}")
            html = res.text

            all_tabs = []
            diag = {}
            for parser in ["html5lib", "bs4", "lxml"]:
                try:
                    tabs = pd.read_html(io.StringIO(html), flavor=parser)
                except Exception:
                    continue
                diag[parser] = len(tabs)
                all_tabs.extend(tabs)
            self.add_debug(f"[wiki] tabelle per parser: {diag} (totale unione={len(all_tabs)})", "info")

            if not all_tabs:
                raise ValueError("read_html non ha trovato alcuna tabella con nessun parser.")

            for idx, tab in enumerate(all_tabs):
                cols_norm = [self._norm_header(c) for c in tab.columns]
                for target in _HEADER_TARGETS:
                    if target in cols_norm:
                        ic = cols_norm.index(target)
                        tickers = [self._clean_val(x) for x in tab[tab.columns[ic]].dropna().astype(str)]
                        tickers = [t for t in tickers if self._is_ticker_like(t)]
                        if len(tickers) >= 10:
                            self.add_debug(f"[wiki] MATCH nome '{target}' tab#{idx} -> {len(tickers)} ticker", "success")
                            return tickers

            best_tab, best_col, best_n = None, None, 0
            for idx, tab in enumerate(all_tabs):
                if tab.empty:
                    continue
                tab_best_col, tab_best_n = None, 0
                for col in tab.columns:
                    vals = tab[col].dropna().astype(str)
                    n = sum(1 for v in vals if self._is_ticker_like(v))
                    if n > tab_best_n:
                        tab_best_n, tab_best_col = n, col
                if tab_best_n > best_n:
                    best_n, best_tab, best_col = tab_best_n, idx, tab_best_col
            if best_n >= 20 and best_tab is not None:
                tickers = [self._clean_val(v) for v in all_tabs[best_tab][best_col].dropna().astype(str)]
                tickers = [t for t in tickers if self._is_ticker_like(t)]
                seen, uniq = set(), []
                for t in tickers:
                    if t not in seen:
                        seen.add(t)
                        uniq.append(t)
                self.add_debug(f"[wiki] EURISTICA tab#{best_tab} colonna '{best_col}' -> {len(uniq)} ticker", "success")
                return uniq

            self.add_debug(f"[wiki] DIAG nessun match: parsers={diag}, best_euristica={best_n} su tab#{best_tab}.", "warning")
            for tab in all_tabs:
                if not tab.empty:
                    tickers = [self._clean_val(t) for t in tab.iloc[:, 0].dropna().astype(str)]
                    tickers = [t for t in tickers if t and t.lower() != 'nan']
                    self.add_debug(f"Usata prima colonna della prima tabella: {len(tickers)} ticker", "warning")
                    return tickers
            raise ValueError("Nessuna colonna identificata.")
        except Exception as e:
            self.add_debug(f"Errore in estrai_ticker_wikipedia: {str(e)}", "error")
            raise

    def normalizza_ticker_europeo(self, ticker_raw, default_suffix):
        t = str(ticker_raw).strip().upper().split()[0]
        if "." in t:
            return t
        return t + default_suffix

    def ottieni_tickers_indice(self, indice_scelto):
        headers = {'User-Agent': 'Mozilla/5.0'}

        if indice_scelto == "S&P 500":
            from_gh = self._read_index_from_github("sp500", suffix="")
            if from_gh and len(from_gh) >= 100:
                return from_gh
            self.add_debug("[sp500] Fallback Wikipedia...", "warning")
            tickers = [t.replace('.', '-') for t in self.estrai_ticker_wikipedia("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", headers)]
            return tickers

        elif indice_scelto == "NASDAQ 100":
            from_gh = self._read_index_from_github("nasdaq100", suffix="")
            if from_gh and len(from_gh) >= 90:
                return from_gh
            self.add_debug("[nasdaq100] Fallback Wikipedia...", "warning")
            raw = self.estrai_ticker_wikipedia("https://en.wikipedia.org/wiki/NASDAQ-100", headers)
            clean = []
            for t in raw:
                t2 = t.replace('.', '-').strip()
                if self._is_ticker_like(t2) and t2 not in clean:
                    clean.append(t2)
            if len(clean) >= 90:
                tickers = clean
                self.add_debug(f"[wiki] NASDAQ-100: uso {len(tickers)} ticker da Wikipedia.", "success")
            else:
                tickers = list(dict.fromkeys(NASDAQ100_STATIC))
                self.add_debug(f"[wiki] NASDAQ-100: Wikipedia ha dato {len(clean)} ticker validi (<90) -> uso lista statica di riserva ({len(tickers)}).", "warning")
            return tickers

        elif indice_scelto == "DAX (Germania)":
            from_gh = self._read_index_from_github("dax", suffix=".DE")
            if from_gh and len(from_gh) >= 40:
                return from_gh
            self.add_debug("[dax] Fallback Wikipedia...", "warning")
            raw = [self.normalizza_ticker_europeo(t, ".DE") for t in self.estrai_ticker_wikipedia("https://en.wikipedia.org/wiki/DAX", headers)]
            seen = set()
            uniq = []
            for t in raw:
                if t not in seen:
                    seen.add(t)
                    uniq.append(t)
            if len(uniq) < 40:
                self.add_debug(f"[wiki] DAX: Wikipedia parziale ({len(uniq)}/40) -> integro con lista statica.", "warning")
                for t in DAX40_STATIC:
                    tt = t + ".DE"
                    if tt not in seen:
                        seen.add(tt)
                        uniq.append(tt)
            tickers = uniq
            self.add_debug(f"[wiki] DAX totale finale: {len(tickers)} ticker.", "info")
            return tickers

        elif indice_scelto == "CAC 40 (Francia)":
            from_gh = self._read_index_from_github("cac40", suffix=".PA")
            if from_gh and len(from_gh) >= 30:
                return from_gh
            self.add_debug("[cac40] Fallback Wikipedia...", "warning")
            tickers = [self.normalizza_ticker_europeo(t, ".PA") for t in self.estrai_ticker_wikipedia("https://en.wikipedia.org/wiki/CAC_40", headers)]
            return tickers

        elif indice_scelto == "FTSE MIB (Italia)":
            from_gh = self._read_index_from_github("ftsemib", suffix=".MI")
            if from_gh and len(from_gh) >= 30:
                return from_gh
            self.add_debug("[ftsemib] Fallback Wikipedia...", "warning")
            tickers = [self.normalizza_ticker_europeo(t, ".MI") for t in self.estrai_ticker_wikipedia("https://en.wikipedia.org/wiki/FTSE_MIB", headers)]
            return tickers

        else:
            raise ValueError(f"Indice non riconosciuto: {indice_scelto}")

    # ===============================
    # DOWNLOAD PREZZI IN BATCH (GIORNALIERO)
    # ===============================
    def download_prices_batch(self, tickers, period="10y", interval="1d"):
        self.add_debug(f"Avvio download batch prezzi per {len(tickers)} ticker (Period: {period}, Interval: {interval})...", "info")
        chunk_size = 50
        chunks = [tickers[i:i + chunk_size] for i in range(0, len(tickers), chunk_size)]
        dfs = []
        for i, chunk in enumerate(chunks):
            self.add_debug(f"Scaricando lotto prezzi {i+1}/{len(chunks)} ({len(chunk)} tickers)...", "info")
            try:
                df_chunk = yf.download(chunk, period=period, interval=interval, progress=False, threads=True, auto_adjust=True)
                if not df_chunk.empty:
                    dfs.append(df_chunk)
                time.sleep(1.0)
            except Exception as e:
                self.add_debug(f"Errore nel lotto prezzi {i+1}: {str(e)}", "error")
        if not dfs:
            return pd.DataFrame()
        try:
            df_total = pd.concat(dfs, axis=1)
            return df_total
        except Exception as e:
            self.add_debug(f"Errore nella concatenazione dei lotti prezzi: {str(e)}", "error")
            return dfs[0] if dfs else pd.DataFrame()

    def get_ticker_history_from_batch(self, df_batch, ticker):
        df_ticker = None
        if not df_batch.empty:
            try:
                if isinstance(df_batch.columns, pd.MultiIndex):
                    if ticker in df_batch.columns.get_level_values(1):
                        df_ticker = pd.DataFrame({
                            'Close': df_batch['Close'][ticker],
                            'High': df_batch['High'][ticker],
                            'Low': df_batch['Low'][ticker],
                            'Volume': df_batch['Volume'][ticker]
                        }).dropna(subset=['Close'])
                    elif ticker in df_batch.columns.get_level_values(0):
                        df_ticker = df_batch[ticker].dropna(subset=['Close'])
                else:
                    df_ticker = df_batch.dropna(subset=['Close'])
            except Exception:
                pass
        if df_ticker is not None and not df_ticker.empty:
            self._save_to_history_cache(ticker, df_ticker)
            return df_ticker
        df_cached = self._load_from_history_cache(ticker)
        if df_cached is not None and not df_cached.empty:
            return df_cached
        return None

    # ===============================
    # FUNDAMENTALS + HEALTH DATA
    # ===============================
    def get_ticker_fundamentals(self, ticker):
        now = datetime.datetime.now()
        if ticker in self.fundamentals_cache:
            cache_entry = self.fundamentals_cache[ticker]
            last_updated_str = cache_entry.get("last_updated")
            if last_updated_str:
                try:
                    last_updated = datetime.datetime.fromisoformat(last_updated_str)
                    if (now - last_updated).days < 14:
                        return cache_entry
                except ValueError:
                    pass
        try:
            self.add_debug(f"Download fondamentali da yfinance per {ticker}...", "info")
            t = yf.Ticker(ticker)
            info = t.info
            mcap = 0
            try:
                mcap = t.fast_info.get('marketCap', 0)
            except Exception:
                pass
            if not mcap:
                mcap = info.get('marketCap', 0)

            net_income = None
            revenue_growth = None
            operating_cf = info.get('operatingCashflow', None)
            try:
                fin = t.financials
                if fin is not None and not fin.empty and 'Net Income' in fin.index:
                    net_income = float(fin.loc['Net Income'].iloc[0])
            except Exception:
                pass
            try:
                qfin = t.quarterly_financials
                if qfin is not None and not qfin.empty and 'Total Revenue' in qfin.index:
                    rev = qfin.loc['Total Revenue']
                    if len(rev) >= 5:
                        current_q = float(rev.iloc[0])
                        prev_q_same = float(rev.iloc[4])
                        if prev_q_same != 0:
                            revenue_growth = (current_q - prev_q_same) / abs(prev_q_same)
            except Exception:
                pass

            entry = {
                "marketCap": mcap,
                "debtToEquity": info.get('debtToEquity', None),
                "freeCashflow": info.get('freeCashflow', None),
                "operatingMargins": info.get('operatingMargins', None),
                "returnOnEquity": info.get('returnOnEquity', None),
                "netIncome": net_income,
                "revenueGrowth": revenue_growth,
                "operatingCashflow": operating_cf,
                "last_updated": now.isoformat()
            }
            self.fundamentals_cache[ticker] = entry
            return entry
        except Exception as e:
            self.add_debug(f"Errore download fondamentali per {ticker}: {str(e)}", "warning")
            if ticker in self.fundamentals_cache:
                return self.fundamentals_cache[ticker]
            return {
                "marketCap": 0, "debtToEquity": None, "freeCashflow": None,
                "operatingMargins": None, "returnOnEquity": None,
                "netIncome": None, "revenueGrowth": None,
                "operatingCashflow": None,
                "last_updated": now.isoformat()
            }

    def fetch_fundamentals_parallel(self, tickers):
        tickers_to_download = []
        now = datetime.datetime.now()
        for ticker in tickers:
            need_download = True
            if ticker in self.fundamentals_cache:
                cache_entry = self.fundamentals_cache[ticker]
                last_updated_str = cache_entry.get("last_updated")
                if last_updated_str:
                    try:
                        last_updated = datetime.datetime.fromisoformat(last_updated_str)
                        if (now - last_updated).days < 14:
                            need_download = False
                    except ValueError:
                        pass
            if need_download:
                tickers_to_download.append(ticker)
        if not tickers_to_download:
            self.add_debug("Tutti i fondamentali sono già presenti in cache valida.", "success")
            return
        self.add_debug(f"Avvio download parallelo per {len(tickers_to_download)} ticker...", "info")
        max_workers = min(12, len(tickers_to_download))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_ticker = {executor.submit(self.get_ticker_fundamentals, ticker): ticker for ticker in tickers_to_download}
            for future in as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    future.result()
                except Exception as exc:
                    self.add_debug(f"Eccezione per {ticker}: {exc}", "warning")
        self.save_cache()

    def compute_health_check(self, ticker):
        fund = self.fundamentals_cache.get(ticker, {})
        score = 0
        opcf = fund.get("operatingCashflow")
        if opcf is not None and opcf > 0:
            score += 1
        rev_g = fund.get("revenueGrowth")
        if rev_g is not None and rev_g > -0.05:
            score += 1
        ni = fund.get("netIncome")
        if ni is not None and ni > 0:
            score += 1
        de = fund.get("debtToEquity")
        if de is not None and de < 3.0:
            score += 1

        if score == 4:
            simbolo = "✅"
        elif score >= 2:
            simbolo = "⚠️"
        else:
            simbolo = "❌"
        codice = f"{simbolo} {score}/4"
        return score, codice

    # ===============================
    # DATI MACRO E BUSSOLA
    # ===============================
    def ottieni_bussola_argo(self):
        try:
            self.add_debug("Download dati macro per Bussola ARGO...", "info")
            macro_tickers = ["^GSPC", "^VIX", "^VVIX"]
            df_macro = yf.download(macro_tickers, period="60d", interval="1d", progress=False)
            if isinstance(df_macro.columns, pd.MultiIndex):
                spx = df_macro['Close']['^GSPC'].dropna()
                vix = df_macro['Close']['^VIX'].dropna()
                vvix = df_macro['Close']['^VVIX'].dropna()
            else:
                spx = df_macro[('Close', '^GSPC')].dropna()
                vix = df_macro[('Close', '^VIX')].dropna()
                vvix = df_macro[('Close', '^VVIX')].dropna()
            common_index = spx.index.intersection(vix.index).intersection(vvix.index)
            spx = spx.loc[common_index]
            vix = vix.loc[common_index]
            vvix = vvix.loc[common_index]
            flip_line = spx.rolling(window=20, min_periods=1).mean()
            ratio = vvix / vix
            latest = {
                "spot": float(spx.iloc[-1]), "vix": float(vix.iloc[-1]),
                "vvx": float(vvix.iloc[-1]), "flip": float(flip_line.iloc[-1]),
                "rapporto": float(ratio.iloc[-1])
            }
            df_res = pd.DataFrame({
                "Date": common_index, "SPX": spx.values, "VIX": vix.values,
                "VVIX": vvix.values, "Flip_Line": flip_line.values, "Ratio": ratio.values
            })
            spot = latest["spot"]; flip = latest["flip"]; rapporto = latest["rapporto"]
            gamma_positivo = spot >= flip
            if gamma_positivo:
                if 5.0 <= rapporto <= 7.0:
                    stato, bias, desc, color = "CORRENTE ASCENDENTE", "LONG", "STRATEGIA: Ingressi Long a pieno regime sui livelli REA.", "emerald"
                elif rapporto < 5.0:
                    stato, bias, desc, color = "CALMA PIATTA", "NEUTRO", "STRATEGIA: Evitare breakout sulla forza. Accumulare solo su supporti.", "slate"
                else:
                    stato, bias, desc, color = "BIVIO STRUTTURALE", "NEUTRO", "STRATEGIA: Blocco nuovi acquisti aggressivi. Alzare i trailing stop.", "amber"
            else:
                if rapporto > 7.0:
                    stato, bias, desc, color = "CASCATA DIREZIONALE", "SHORT", "STRATEGIA: BLOCCO TOTALE DEGLI ACQUISTI. Proteggere il capitale.", "rose"
                elif rapporto < 5.0:
                    stato, bias, desc, color = "RIMBALZO ELASTICO", "LONG", "STRATEGIA: Esaurimento del panico. Ingressi Long veloci (size dimezzata).", "indigo"
                else:
                    stato, bias, desc, color = "CORRENTE DISCENDENTE", "SHORT", "STRATEGIA: Operatività ridotta del 50%. Accumulo ultra-paziente.", "orange"
            bussola = {"spot": spot, "vix": latest["vix"], "vvx": latest["vvx"], "flip": flip, "rapporto": rapporto, "stato": stato, "bias": bias, "desc": desc, "color": color}
            return {"df": df_res, "latest": latest, "bussola": bussola}
        except Exception as e:
            self.add_debug(f"Errore dati macro, uso simulazione: {str(e)}", "warning")
            dates = pd.date_range(end=datetime.datetime.today(), periods=30, freq='D')
            latest = {"spot": 5472.79, "vix": 20.21, "vvx": 91.72, "flip": 5450.0, "rapporto": 4.54}
            bussola = {"spot": latest["spot"], "vix": latest["vix"], "vvx": latest["vvx"], "flip": latest["flip"], "rapporto": latest["rapporto"], "stato": "RIMBALZO ELASTICO", "bias": "LONG", "desc": "STRATEGIA: Esaurimento del panico. Ingressi Long veloci (size dimezzata).", "color": "indigo"}
            return {"df": pd.DataFrame({"Date": dates, "SPX": np.linspace(5400, 5472, 30), "VIX": np.linspace(20, 20.21, 30), "VVIX": np.linspace(90, 91.72, 30), "Flip_Line": np.linspace(5380, 5450, 30), "Ratio": np.linspace(4.5, 4.54, 30)}), "latest": latest, "bussola": bussola}

    # ===============================
    # FUNZIONI DI CALCOLO REA
    # ===============================
    def find_structural_lows(self, hist):
        df = hist.copy()
        df.index = pd.to_datetime(df.index)
        df["Year"] = df.index.year
        yearly = {}
        for year, group in df.groupby("Year"):
            min_idx_label = group["Low"].idxmin()
            bar_pos = df.index.get_loc(min_idx_label)
            if isinstance(bar_pos, slice):
                bar_pos = bar_pos.start
            elif hasattr(bar_pos, '__len__'):
                bar_pos = int(bar_pos[0])
            else:
                bar_pos = int(bar_pos)
            yearly[year] = (bar_pos, float(group["Low"].min()), min_idx_label)
        years_sorted = sorted(yearly.keys())
        n_years = len(years_sorted)
        filtered = []
        if not years_sorted:
            return filtered
        first_year = years_sorted[0]
        bar_pos, price, date = yearly[first_year]
        filtered.append((bar_pos, price, 0.0, date))
        i = 1
        while i < n_years:
            year = years_sorted[i]
            prev_year = years_sorted[i - 1]
            if yearly[year][1] < yearly[prev_year][1]:
                j = i
                while j + 1 < n_years and yearly[years_sorted[j + 1]][1] < yearly[years_sorted[j]][1]:
                    j += 1
                end_year = years_sorted[j]
                bar_pos, price, date = yearly[end_year]
                prev_high = float(df["High"].iloc[:bar_pos].max()) if bar_pos > 0 else price
                drop = (prev_high - price) / prev_high * 100 if prev_high > price else 0.0
                filtered.append((bar_pos, price, drop, date))
                i = j + 1
            else:
                i += 1
        if len(filtered) < 3:
            included_bar_positions = {f[0] for f in filtered}
            candidates = []
            for yr, val in yearly.items():
                b_pos, pr, dt = val
                if b_pos not in included_bar_positions:
                    prev_high = float(df["High"].iloc[:b_pos].max()) if b_pos > 0 else pr
                    drop = (prev_high - pr) / prev_high * 100 if prev_high > pr else 0.0
                    candidates.append((b_pos, pr, drop, dt))
            candidates.sort(key=lambda x: x[1])
            needed = 3 - len(filtered)
            for c in candidates[:needed]:
                filtered.append(c)
        filtered.sort(key=lambda x: x[3])
        return filtered

    def compute_vwap_levels(self, hist):
        if hist.empty or len(hist) < WIN_VWAP_3M:
            return {"vwap_4y": None, "vwap_1y": None, "vwap_3m": None, "dist_4y_pct": None, "dist_1y_pct": None, "dist_3m_pct": None, "convergence_count": 0, "convergence_label": "N/D"}
        df = hist.copy()
        current_price = float(df['Close'].iloc[-1])
        high = df['High'].astype(float); low = df['Low'].astype(float)
        close = df['Close'].astype(float); volume = df['Volume'].astype(float)
        typical_price = (high + low + close) / 3.0
        tpv = typical_price * volume

        def calc_vwap(sub_tpv, sub_vol):
            vol_sum = sub_vol.sum()
            if vol_sum == 0:
                return current_price
            return float(sub_tpv.sum() / vol_sum)

        n_3m = min(WIN_VWAP_3M, len(df)); vwap_3m = calc_vwap(tpv.iloc[-n_3m:], volume.iloc[-n_3m:])
        n_1y = min(WIN_VWAP_1Y, len(df)); vwap_1y = calc_vwap(tpv.iloc[-n_1y:], volume.iloc[-n_1y:])
        n_4y = min(WIN_VWAP_4Y, len(df)); vwap_4y = calc_vwap(tpv.iloc[-n_4y:], volume.iloc[-n_4y:])
        dist_3m = (current_price - vwap_3m) / vwap_3m * 100
        dist_1y = (current_price - vwap_1y) / vwap_1y * 100
        dist_4y = (current_price - vwap_4y) / vwap_4y * 100
        near_threshold = 3.5
        near_vwaps = [abs(dist_3m) <= near_threshold, abs(dist_1y) <= near_threshold, abs(dist_4y) <= near_threshold]
        convergence_count = sum(near_vwaps)
        if convergence_count >= 3:
            conv_label = "🔥 ALTA (3 VWAP vicini)"
        elif convergence_count == 2:
            conv_label = "⚡ MEDIA (2 VWAP vicini)"
        elif convergence_count == 1:
            conv_label = "🔹 BASE (1 VWAP vicino)"
        else:
            conv_label = "⚪ NESSUNA"
        return {"vwap_4y": round(vwap_4y, 2), "vwap_1y": round(vwap_1y, 2), "vwap_3m": round(vwap_3m, 2), "dist_4y_pct": round(dist_4y, 1), "dist_1y_pct": round(dist_1y, 1), "dist_3m_pct": round(dist_3m, 1), "convergence_count": convergence_count, "convergence_label": conv_label}

    def compute_poc_with_zone(self, hist, start_idx, end_idx, n_bins=60):
        segment = hist.iloc[start_idx:end_idx]
        if len(segment) < 2:
            return None, None, None

        low = segment["Low"].to_numpy(dtype=float)
        high = segment["High"].to_numpy(dtype=float)
        volume = segment["Volume"].to_numpy(dtype=float)
        price_min = float(np.nanmin(low))
        price_max = float(np.nanmax(high))

        if price_max <= price_min:
            return None, None, None

        bins = np.linspace(price_min, price_max, n_bins + 1)
        bin_centers = (bins[:-1] + bins[1:]) / 2
        bw = bins[1] - bins[0]

        bar_range = high - low
        valid = (bar_range > 0) & np.isfinite(bar_range) & np.isfinite(volume)
        if not valid.any():
            return None, None, None

        low = low[valid]
        high = high[valid]
        volume = volume[valid]
        bar_range = bar_range[valid]

        b_lo = np.clip(np.searchsorted(bins, low, side='right') - 1, 0, n_bins - 1)
        b_hi = np.clip(np.searchsorted(bins, high, side='left') - 1, 0, n_bins - 1)

        acc = np.zeros(n_bins)
        same = (b_lo == b_hi)
        np.add.at(acc, b_lo[same], volume[same])

        multi = ~same
        if multi.any():
            lo = b_lo[multi]
            hi = b_hi[multi]
            vol_m = volume[multi]
            rng_m = bar_range[multi]
            frac_lo = (bins[lo + 1] - low[multi]) / rng_m
            np.add.at(acc, lo, vol_m * frac_lo)
            frac_hi = (high[multi] - bins[hi]) / rng_m
            np.add.at(acc, hi, vol_m * frac_hi)
            unit = vol_m * bw / rng_m
            events = np.zeros(n_bins + 1)
            np.add.at(events, lo + 1, unit)
            np.add.at(events, hi, -unit)
            acc += np.cumsum(events)[:n_bins]

        poc_idx = int(np.argmax(acc))
        poc_price = float(bin_centers[poc_idx])

        poc_volume = acc[poc_idx]
        max_volume = float(acc.max())
        threshold_rel = ZONE_MIN_PCT * poc_volume
        threshold_abs = (LVN_FLOOR_PCT * max_volume) if USE_LVN_EDGE else -np.inf
        threshold = max(threshold_rel, threshold_abs)

        lo_idx = poc_idx
        while lo_idx - 1 >= 0 and acc[lo_idx - 1] >= threshold:
            lo_idx -= 1
        hi_idx = poc_idx
        while hi_idx + 1 < n_bins and acc[hi_idx + 1] >= threshold:
            hi_idx += 1

        return poc_price, float(bin_centers[lo_idx]), float(bin_centers[hi_idx])

    def get_pocs_from_hist(self, hist, n_bins=60):
        if hist.empty or len(hist) < 10:
            return []
        structural_lows = self.find_structural_lows(hist)
        total_bars = len(hist)
        current_year = datetime.datetime.now().year
        pocs = []

        for bar_pos, low_price, drop, anchor_date in structural_lows:
            poc_price, poc_low, poc_high = self.compute_poc_with_zone(hist, bar_pos, total_bars, n_bins=n_bins)
            if poc_price is None:
                continue

            years_ago = max(current_year - anchor_date.year, 0)
            age_weight = 1.0 + np.log1p(years_ago)
            drop_weight = 1.0 + (drop / 50.0)
            segment_bars = total_bars - bar_pos
            bar_weight = 1.0 + np.log1p(segment_bars / BARS_PER_YEAR)
            raw_weight = age_weight * drop_weight * bar_weight

            pocs.append({
                "anchor_year": int(anchor_date.year),
                "anchor_date": anchor_date,
                "drop_pct": round(float(drop), 1),
                "poc_price": round(float(poc_price), 4),
                "poc_low": round(float(poc_low), 4),
                "poc_high": round(float(poc_high), 4),
                "weight": float(raw_weight)
            })

        if pocs:
            max_w = max(p["weight"] for p in pocs)
            min_w = min(p["weight"] for p in pocs)
            for p in pocs:
                if max_w > min_w:
                    p["weight_norm"] = round(1 + 9 * (p["weight"] - min_w) / (max_w - min_w), 1)
                else:
                    p["weight_norm"] = 5.0

        return pocs

    def closest_poc(self, pocs, current_price, max_dist_pct=MAX_POC_DIST_PCT):
        if not pocs:
            return None, None
        best_poc = None
        best_dist = None
        for poc in pocs:
            poc_price = float(poc["poc_price"])
            dist = (current_price - poc_price) / poc_price * 100
            if abs(dist) > max_dist_pct:
                continue
            if best_dist is None or abs(dist) < abs(best_dist):
                best_dist = dist
                best_poc = poc
        if best_poc is None:
            return None, None
        return best_poc, round(float(best_dist), 2)

    def top_operative_pocs(self, pocs, current_price, n=N_POC_WATCHLIST, max_dist_pct=MAX_POC_DIST_PCT, merge_pct=POC_MERGE_PCT):
        ops = []
        for poc in pocs:
            poc_price = float(poc["poc_price"])
            dist = (current_price - poc_price) / poc_price * 100
            if abs(dist) <= max_dist_pct:
                ops.append((
                    float(poc.get("weight_norm", 0.0)), abs(dist), poc_price,
                    float(poc.get("poc_low", poc_price)), float(poc.get("poc_high", poc_price)),
                    int(poc["anchor_year"])
                ))

        ops.sort(key=lambda x: x[0], reverse=True)
        chosen = []
        for wn, d, price, low, high, yr in ops:
            if all(abs(price - c["poc_price"]) / c["poc_price"] * 100 > merge_pct for c in chosen):
                chosen.append({
                    "poc_price": price,
                    "poc_low": low,
                    "poc_high": high,
                    "anchor_year": yr,
                    "dist_pct": round((current_price - price) / price * 100, 2),
                })
                if len(chosen) >= n:
                    break
        return chosen

    def calcola_segnali_bottom(self, hist):
        if len(hist) < WIN_ROC + 5:
            return 0, "Dati insufficienti"
        close = hist['Close'].astype(float)
        volume = hist['Volume'].astype(float)
        score = 0
        dettagli = []

        roc = close.pct_change(periods=WIN_ROC) * 100
        roc_current = roc.iloc[-1]
        roc_before = roc.iloc[-WIN_ROC_COMPARE] if len(roc) >= WIN_ROC_COMPARE else roc_current
        if not pd.isna(roc_current) and not pd.isna(roc_before) and roc_current > roc_before:
            score += 1
            dettagli.append(f"Decelerazione (ROC: {roc_current:.1f}% > {roc_before:.1f}%)")

        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        histogram = macd - signal
        if len(histogram) >= 2 and histogram.iloc[-1] > histogram.iloc[-2]:
            score += 1
            dettagli.append("MACD Histogram in risalita")

        try:
            pocs = self.get_pocs_from_hist(hist)
            vwap_info = self.compute_vwap_levels(hist)
            poc_op, dist_op = self.closest_poc(pocs, float(close.iloc[-1]))

            if poc_op is not None:
                wn = float(poc_op.get("weight_norm", 0.0))
                mom_up = close.iloc[-1] > close.iloc[-min(WIN_MOM, len(close) - 1)]
                poc_low = float(poc_op.get("poc_low", poc_op["poc_price"]))
                poc_high = float(poc_op.get("poc_high", poc_op["poc_price"]))
                price_now = float(close.iloc[-1])

                in_zone = poc_low <= price_now <= poc_high
                near_poc = abs(dist_op) < 3

                if (in_zone or near_poc) and wn >= MIN_POC_WEIGHT_NORM and mom_up:
                    score += 1
                    dettagli.append(f"Vicino/In zona POC ({abs(dist_op):.1f}%)")

            if vwap_info["convergence_count"] >= 2:
                score += 1
                dettagli.append(f"Convergenza VWAP ({vwap_info['convergence_label']})")
        except Exception:
            pass

        if len(volume) >= WIN_VOL + 1:
            vol_ultimo = volume.iloc[-1]
            vol_media = volume.iloc[-(WIN_VOL + 1):-1].mean()
            if len(close) >= 3:
                force_index = (close.iloc[-1] - close.iloc[-2]) * volume.iloc[-1]
                force_prev = (close.iloc[-2] - close.iloc[-3]) * volume.iloc[-2]
                if vol_media > 0 and vol_ultimo > 1.3 * vol_media and force_index > force_prev:
                    score += 1
                    dettagli.append("Volume e Forza in aumento")

        return int(score), ", ".join(dettagli) if dettagli else "Nessun segnale"

    # ===============================
    # MOTORE DI SCREENING (singolo indice — usato dall'UI manuale)
    # ===============================
    def perform_screening(self, indice_scelto, min_market_cap, soglia_drawdown, soglia_poc_pct):
        self.add_debug(f"🚀 Avvio screening ottimizzato per {indice_scelto}...", "info")
        try:
            tickers = self.ottieni_tickers_indice(indice_scelto)
            self.add_debug(f"Trovati {len(tickers)} ticker.", "info")
        except Exception as e:
            self.add_debug(f"Errore nel recupero dei ticker: {e}", "error")
            return [], []

        problematic_tickers = ["INWH", "MRSH", "INW", "INVH", "MRNA", "REGN", "SPOT"]
        problematic_patterns = ["INVH", "MRSH", "INWH", "INW"]
        clean_tickers = []
        for t in tickers:
            skip = False
            for pat in problematic_patterns:
                if pat in t:
                    skip = True
                    break
            if t in problematic_tickers:
                skip = True
            if not skip:
                clean_tickers.append(t)

        self.add_debug(f"Ticker puliti per il download: {len(clean_tickers)}", "info")
        df_batch = self.download_prices_batch(clean_tickers)
        if df_batch.empty:
            self.add_debug("Nessun dato scaricato da yfinance. Verrà tentata l'analisi offline con la cache locale...", "warning")

        candidates = []
        candidates_hist = {}
        self.add_debug("Calcolo drawdown e filtraggio preliminare...", "info")

        for ticker in clean_tickers:
            hist = self.get_ticker_history_from_batch(df_batch, ticker)
            if hist is None or len(hist) < 10:
                continue

            close_series = hist['Close'].dropna()
            high_series = hist['High'].dropna()

            if close_series.empty or high_series.empty:
                continue

            price_now = float(close_series.values[-1])
            ath_value = float(high_series.max())
            current_dd = ((price_now - ath_value) / ath_value) * 100

            if current_dd <= -soglia_drawdown:
                candidates.append(ticker)
                candidates_hist[ticker] = {"hist": hist, "price_now": price_now, "current_dd": current_dd}

        self.add_debug(f"Trovati {len(candidates)} candidati in forte drawdown (>= {soglia_drawdown}%).", "success")
        if not candidates:
            self.add_debug("Nessun candidato ha superato il filtro del drawdown.", "warning")
            return [], []

        self.fetch_fundamentals_parallel(candidates)
        pre_filtered = []
        is_europe = indice_scelto in ["DAX (Germania)", "CAC 40 (Francia)", "FTSE MIB (Italia)"]

        for ticker in candidates:
            fund = self.fundamentals_cache.get(ticker, {})
            mcap = fund.get("marketCap", 0) or 0
            if not is_europe and mcap < min_market_cap:
                continue

            c_data = candidates_hist[ticker]
            hist = c_data["hist"]
            price_now = c_data["price_now"]
            current_dd = c_data["current_dd"]

            poc_label, dist_label, alert_poc = "N/D", "N/D", ""
            poc_slots = {f"POC {k}": 0.0 for k in (1, 2, 3)}
            poc_low_slots = {f"POC {k} Low": 0.0 for k in (1, 2, 3)}
            poc_high_slots = {f"POC {k} High": 0.0 for k in (1, 2, 3)}
            poc_note_slots = {f"Nota POC {k}": "" for k in (1, 2, 3)}

            try:
                pocs = self.get_pocs_from_hist(hist)
                poc_vicino, dist_poc_pct = self.closest_poc(pocs, price_now)

                if poc_vicino is not None:
                    poc_label = f"{poc_vicino['poc_price']:.2f} ({poc_vicino['anchor_year']})"
                    dist_label = f"{dist_poc_pct:+.1f}%"
                    wn_vicino = float(poc_vicino.get("weight_norm", 0.0))

                    poc_low = float(poc_vicino.get("poc_low", poc_vicino["poc_price"]))
                    poc_high = float(poc_vicino.get("poc_high", poc_vicino["poc_price"]))
                    in_zone = poc_low <= price_now <= poc_high
                    near_poc = abs(dist_poc_pct) <= soglia_poc_pct

                    if (in_zone or near_poc) and wn_vicino >= MIN_POC_WEIGHT_NORM:
                        alert_poc = "🎯 SU POC"

                top3 = self.top_operative_pocs(pocs, price_now, n=N_POC_WATCHLIST)
                for k, item in enumerate(top3, start=1):
                    poc_slots[f"POC {k}"] = round(float(item["poc_price"]), 4)
                    poc_low_slots[f"POC {k} Low"] = round(float(item["poc_low"]), 4)
                    poc_high_slots[f"POC {k} High"] = round(float(item["poc_high"]), 4)
                    poc_note_slots[f"Nota POC {k}"] = f"POC {item['anchor_year']}"
            except Exception as e:
                self.add_debug(f"Errore calcolo POC per {ticker}: {e}", "warning")

            bottom_score, bottom_dettagli = self.calcola_segnali_bottom(hist)
            vwap_info = self.compute_vwap_levels(hist)

            pre_filtered.append({
                "Ticker": ticker,
                "Indice": indice_scelto,
                "Prezzo": round(price_now, 2),
                "Drawdown (%)": round(current_dd, 2),
                "Market Cap (B)": round(mcap / 1e9, 2) if mcap > 0 else 0.0,
                "POC più vicino": poc_label,
                "Distanza POC (%)": dist_label,
                "🎯 ALERT POC": alert_poc,
                **poc_slots,
                **poc_low_slots,
                **poc_high_slots,
                **poc_note_slots,
                "VWAP 4Y": vwap_info["vwap_4y"],
                "VWAP 1Y": vwap_info["vwap_1y"],
                "VWAP 3M": vwap_info["vwap_3m"],
                "Convergenza VWAP": vwap_info["convergence_label"],
                "Bottom Score (0-4)": bottom_score,
                "Bottom Dettagli": bottom_dettagli,
            })

        self.add_debug(f"Pre-filtrati rimasti dopo Market Cap: {len(pre_filtered)}", "info")
        if not pre_filtered:
            return [], []

        macro_info = self.ottieni_bussola_argo()
        argo_bussola = macro_info["bussola"]
        final_list = []
        spostamenti_rilevati = []

        for item in pre_filtered:
            ticker = item["Ticker"]

            health_score, health_code = self.compute_health_check(ticker)
            item["Health"] = health_code
            item["Health_Score"] = health_score

            mcap_val = item["Market Cap (B)"]
            base_size = 10.0 if mcap_val >= 10.0 else (5.0 if mcap_val >= 2.0 else 2.0)
            size_mult = 1.2 if health_score >= 3 else (1.0 if health_score >= 2 else 0.6)
            argo_mult = 0.3 if argo_bussola['bias'] == "SHORT" else (0.6 if argo_bussola['bias'] == "NEUTRO" else 1.0)
            final_size = round(base_size * size_mult * argo_mult, 1)
            if final_size < 1.0:
                final_size = 0.0
            item["Size Suggerita (%)"] = float(final_size)

            dist_label = item["Distanza POC (%)"]
            if dist_label != "N/D":
                try:
                    dist_val = float(dist_label.replace("%", "").replace("+", ""))
                    if abs(dist_val) <= 1.5:
                        entry_mode = "🚀 MARKET (vicino POC)"
                    elif dist_val < -1.5:
                        entry_mode = "⏳ LIMITE (sotto POC, attendere)"
                    else:
                        entry_mode = "📈 LIMITE (sopra POC, pazienza)"
                except Exception:
                    entry_mode = "🔍 VERIFICA MANUALE"
            else:
                entry_mode = "🔍 VERIFICA MANUALE"

            if argo_bussola['bias'] == "SHORT":
                entry_mode = "⛔ SHORT (NON ENTRARE)" if final_size == 0 else "⏳ LIMITE (size ridotta)"

            item["Entry Mode"] = str(entry_mode)
            status_precedente = self.screener_state.get(ticker, {}).get("status", None)

            if item["Drawdown (%)"] <= -soglia_drawdown:
                item["Stato"] = "Active"
                if status_precedente == "Ripartito":
                    spostamenti_rilevati.append(f"⚠️ **{ticker}** ({indice_scelto}) è rientrata in Forte Sconto.")
                self.screener_state[ticker] = {"status": "Active", "indice": indice_scelto}
            else:
                if status_precedente == "Active":
                    item["Stato"] = "Ripartito"
                    spostamenti_rilevati.append(f"🚀 **{ticker}** ({indice_scelto}) è passata in Ripartenza.")
                    self.screener_state[ticker] = {"status": "Ripartito", "indice": indice_scelto}
                elif status_precedente == "Ripartito":
                    item["Stato"] = "Ripartito"
                else:
                    item["Stato"] = "Nuovo"

            final_list.append(item)

        self.screener_database[indice_scelto] = final_list
        if "_last_scans" not in self.screener_database:
            self.screener_database["_last_scans"] = {}
        self.screener_database["_last_scans"][indice_scelto] = datetime.datetime.now().isoformat()
        self.save_all()
        self.add_debug(f"✅ Screening completato per {indice_scelto}. {len(final_list)} titoli registrati.", "success")

        return final_list, spostamenti_rilevati

    # ===============================
    # MOTORE MULTI-INDICE (usato dal cron — UN solo download prezzi per tutti gli indici)
    # ===============================
    def perform_screening_multi(self, indici, min_market_cap, soglia_drawdown, soglia_poc_pct):
        self.add_debug(f"🚀 Screening MULTI-INDICE su {len(indici)} indici...", "info")

        tickers_per_indice = {}
        global_set = set()
        problematic_tickers = ["INWH", "MRSH", "INW", "INVH", "MRNA", "REGN", "SPOT"]
        problematic_patterns = ["INVH", "MRSH", "INWH", "INW"]

        for idx in indici:
            try:
                raw = self.ottieni_tickers_indice(idx)
            except Exception as e:
                self.add_debug(f"[multi] Errore ticker {idx}: {e}", "error")
                raw = []
            clean = []
            for t in raw:
                skip = False
                for pat in problematic_patterns:
                    if pat in t:
                        skip = True
                        break
                if t in problematic_tickers or skip:
                    continue
                clean.append(t)
            tickers_per_indice[idx] = clean
            global_set.update(clean)
            self.add_debug(f"[multi] {idx}: {len(clean)} ticker puliti", "info")

        global_tickers = sorted(global_set)
        self.add_debug(f"[multi] Totale ticker unici da scaricare: {len(global_tickers)}", "success")

        if not global_tickers:
            return {idx: ([], []) for idx in indici}

        df_batch = self.download_prices_batch(global_tickers)
        if df_batch.empty:
            self.add_debug("[multi] Batch prezzi vuoto — proseguo con cache storica.", "warning")

        results = {}
        macro_info = self.ottieni_bussola_argo()
        argo_bussola = macro_info["bussola"]

        for idx in indici:
            clean_tickers = tickers_per_indice[idx]
            is_europe = idx in ["DAX (Germania)", "CAC 40 (Francia)", "FTSE MIB (Italia)"]

            candidates = []
            candidates_hist = {}
            for ticker in clean_tickers:
                hist = self.get_ticker_history_from_batch(df_batch, ticker)
                if hist is None or len(hist) < 10:
                    continue
                close_s = hist['Close'].dropna()
                high_s = hist['High'].dropna()
                if close_s.empty or high_s.empty:
                    continue
                price_now = float(close_s.values[-1])
                ath = float(high_s.max())
                dd = ((price_now - ath) / ath) * 100
                if dd <= -soglia_drawdown:
                    candidates.append(ticker)
                    candidates_hist[ticker] = {"hist": hist, "price_now": price_now, "current_dd": dd}

            self.add_debug(f"[multi] {idx}: {len(candidates)} candidati in drawdown >= {soglia_drawdown}%", "info")
            if not candidates:
                self.screener_database[idx] = []
                self.screener_database.setdefault("_last_scans", {})[idx] = datetime.datetime.now().isoformat()
                results[idx] = ([], [])
                continue

            self.fetch_fundamentals_parallel(candidates)

            pre_filtered = []
            for ticker in candidates:
                fund = self.fundamentals_cache.get(ticker, {})
                mcap = fund.get("marketCap", 0) or 0
                if not is_europe and mcap < min_market_cap:
                    continue
                c_data = candidates_hist[ticker]
                hist = c_data["hist"]; price_now = c_data["price_now"]; current_dd = c_data["current_dd"]

                poc_label, dist_label, alert_poc = "N/D", "N/D", ""
                poc_slots = {f"POC {k}": 0.0 for k in (1, 2, 3)}
                poc_low_slots = {f"POC {k} Low": 0.0 for k in (1, 2, 3)}
                poc_high_slots = {f"POC {k} High": 0.0 for k in (1, 2, 3)}
                poc_note_slots = {f"Nota POC {k}": "" for k in (1, 2, 3)}
                try:
                    pocs = self.get_pocs_from_hist(hist)
                    poc_vicino, dist_poc_pct = self.closest_poc(pocs, price_now)
                    if poc_vicino is not None:
                        poc_label = f"{poc_vicino['poc_price']:.2f} ({poc_vicino['anchor_year']})"
                        dist_label = f"{dist_poc_pct:+.1f}%"
                        wn_vicino = float(poc_vicino.get("weight_norm", 0.0))
                        poc_low = float(poc_vicino.get("poc_low", poc_vicino["poc_price"]))
                        poc_high = float(poc_vicino.get("poc_high", poc_vicino["poc_price"]))
                        in_zone = poc_low <= price_now <= poc_high
                        near_poc = abs(dist_poc_pct) <= soglia_poc_pct
                        if (in_zone or near_poc) and wn_vicino >= MIN_POC_WEIGHT_NORM:
                            alert_poc = "🎯 SU POC"
                    top3 = self.top_operative_pocs(pocs, price_now, n=N_POC_WATCHLIST)
                    for k, item in enumerate(top3, start=1):
                        poc_slots[f"POC {k}"] = round(float(item["poc_price"]), 4)
                        poc_low_slots[f"POC {k} Low"] = round(float(item["poc_low"]), 4)
                        poc_high_slots[f"POC {k} High"] = round(float(item["poc_high"]), 4)
                        poc_note_slots[f"Nota POC {k}"] = f"POC {item['anchor_year']}"
                except Exception as e:
                    self.add_debug(f"[multi] Errore POC per {ticker}: {e}", "warning")

                bottom_score, bottom_dettagli = self.calcola_segnali_bottom(hist)
                vwap_info = self.compute_vwap_levels(hist)
                pre_filtered.append({
                    "Ticker": ticker, "Indice": idx,
                    "Prezzo": round(price_now, 2), "Drawdown (%)": round(current_dd, 2),
                    "Market Cap (B)": round(mcap / 1e9, 2) if mcap > 0 else 0.0,
                    "POC più vicino": poc_label, "Distanza POC (%)": dist_label, "🎯 ALERT POC": alert_poc,
                    **poc_slots, **poc_low_slots, **poc_high_slots, **poc_note_slots,
                    "VWAP 4Y": vwap_info["vwap_4y"], "VWAP 1Y": vwap_info["vwap_1y"], "VWAP 3M": vwap_info["vwap_3m"],
                    "Convergenza VWAP": vwap_info["convergence_label"],
                    "Bottom Score (0-4)": bottom_score, "Bottom Dettagli": bottom_dettagli,
                })

            self.add_debug(f"[multi] {idx}: {len(pre_filtered)} pre-filtrati", "info")
            if not pre_filtered:
                self.screener_database[idx] = []
                self.screener_database.setdefault("_last_scans", {})[idx] = datetime.datetime.now().isoformat()
                results[idx] = ([], [])
                continue

            final_list = []
            spostamenti_rilevati = []
            for item in pre_filtered:
                ticker = item["Ticker"]
                hs, hc = self.compute_health_check(ticker)
                item["Health"] = hc; item["Health_Score"] = hs
                mv = item["Market Cap (B)"]
                bs = 10.0 if mv >= 10.0 else (5.0 if mv >= 2.0 else 2.0)
                sm = 1.2 if hs >= 3 else (1.0 if hs >= 2 else 0.6)
                am = 0.3 if argo_bussola['bias'] == "SHORT" else (0.6 if argo_bussola['bias'] == "NEUTRO" else 1.0)
                fs = round(bs * sm * am, 1)
                if fs < 1.0:
                    fs = 0.0
                item["Size Suggerita (%)"] = float(fs)
                dl = item["Distanza POC (%)"]
                if dl != "N/D":
                    try:
                        dv = float(dl.replace("%", "").replace("+", ""))
                        if abs(dv) <= 1.5:
                            em = "🚀 MARKET (vicino POC)"
                        elif dv < -1.5:
                            em = "⏳ LIMITE (sotto POC, attendere)"
                        else:
                            em = "📈 LIMITE (sopra POC, pazienza)"
                    except Exception:
                        em = "🔍 VERIFICA MANUALE"
                else:
                    em = "🔍 VERIFICA MANUALE"
                if argo_bussola['bias'] == "SHORT":
                    em = "⛔ SHORT (NON ENTRARE)" if fs == 0 else "⏳ LIMITE (size ridotta)"
                item["Entry Mode"] = str(em)

                st_prec = self.screener_state.get(ticker, {}).get("status", None)
                if item["Drawdown (%)"] <= -soglia_drawdown:
                    item["Stato"] = "Active"
                    if st_prec == "Ripartito":
                        spostamenti_rilevati.append(f"⚠️ **{ticker}** ({idx}) è rientrata in Forte Sconto.")
                    self.screener_state[ticker] = {"status": "Active", "indice": idx}
                else:
                    if st_prec == "Active":
                        item["Stato"] = "Ripartito"
                        spostamenti_rilevati.append(f"🚀 **{ticker}** ({idx}) è passata in Ripartenza.")
                        self.screener_state[ticker] = {"status": "Ripartito", "indice": idx}
                    elif st_prec == "Ripartito":
                        item["Stato"] = "Ripartito"
                    else:
                        item["Stato"] = "Nuovo"
                final_list.append(item)

            self.screener_database[idx] = final_list
            self.screener_database.setdefault("_last_scans", {})[idx] = datetime.datetime.now().isoformat()
            results[idx] = (final_list, spostamenti_rilevati)
            self.add_debug(f"[multi] ✅ {idx}: {len(final_list)} titoli registrati.", "success")

        self.save_all()
        total = sum(len(r[0]) for r in results.values())
        self.add_debug(f"[multi] ✅ Screening multi completato: {total} titoli totali su {len(indici)} indici.", "success")
        return results
