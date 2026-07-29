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

# === FINESTRE TEMPORALI (in barre daily = giorni di trading) ===
BARS_PER_YEAR = 252
WIN_VWAP_3M = 63
WIN_VWAP_1Y = 252
WIN_VWAP_4Y = 1008
WIN_ROC = 70
WIN_ROC_COMPARE = 15
WIN_VOL = 25
WIN_MOM = 5

# Intestazioni di colonna accettate (già normalizzate: solo lettere e spazi)
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

    # ---------- helper normalizzazione (per l'estrazione ticker) ----------
    def _norm_header(self, s):
        """Riduce un'intestazione a solo lettere+spazi: 'Ticker symbol[1]' -> 'ticker symbol'."""
        s = str(s)
        s = re.sub(r"\s+", " ", s).strip()      # \n, \t -> spazio
        s = re.sub(r"\[[^\]]*\]", "", s)         # via note [n]
        s = re.sub(r"\([^)]*\)", "", s)          # via note (n)
        s = s.lower()
        s = re.sub(r"[^a-z ]", "", s)            # solo lettere e spazi
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def _clean_val(self, s):
        """Pulisce un valore di cella: toglie spazi invisibili, note, caratteri non-ASCII."""
        s = str(s)
        s = s.split("[")[0]                      # via note tipo AAPL[5]
        s = re.sub(r"\s+", "", s)                # i ticker non hanno spazi
        s = s.encode("ascii", "ignore").decode() # via caratteri non-ASCII
        return s.strip()

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
    # ESTRAZIONE TICKERS (multi-parser: html5lib -> bs4 -> lxml)
    # ===============================
    def estrai_ticker_wikipedia(self, url, headers=None):
        headers = headers or {'User-Agent': 'Mozilla/5.0'}
        self.add_debug(f"Estrazione ticker da: {url}", "info")
        try:
            res = requests.get(url, headers=headers, timeout=30)
            if res.status_code != 200:
                raise ConnectionError(f"Wikipedia ha risposto con codice {res.status_code}")
            html = res.text

            # Provo i parser in cascata e UNISCO le tabelle: html5lib cattura le
            # tabelle "complesse" (es. componenti NASDAQ-100) che lxml salta.
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

            # 1) Match per NOME di colonna (intestazione normalizzata)
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

            # 2) Euristica sui VALORI: colonna con più sigle ticker-like, su tutte le tabelle
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

            # 3) Diagnostica + ultima ratio (prima colonna della prima tabella non vuota)
            self.add_debug(f"[wiki] DIAG nessun match: parsers={diag}, best_euristica={best_n} su tab#{best_tab}. Verifica che 'html5lib' sia in requirements.", "warning")
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
        t = str(ticker_raw).strip().split()[0]
        if "." in t:
            return t
        return t + default_suffix

    def ottieni_tickers_indice(self, indice_scelto):
        headers = {'User-Agent': 'Mozilla/5.0'}
        if indice_scelto == "S&P 500":
            tickers = [t.replace('.', '-') for t in self.estrai_ticker_wikipedia("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", headers)]
        elif indice_scelto == "NASDAQ 100":
            tickers = [t.replace('.', '-') for t in self.estrai_ticker_wikipedia("https://en.wikipedia.org/wiki/NASDAQ-100", headers)]
        elif indice_scelto == "DAX (Germania)":
            tickers = [self.normalizza_ticker_europeo(t, ".DE") for t in self.estrai_ticker_wikipedia("https://en.wikipedia.org/wiki/DAX", headers)]
        elif indice_scelto == "CAC 40 (Francia)":
            tickers = [self.normalizza_ticker_europeo(t, ".PA") for t in self.estrai_ticker_wikipedia("https://en.wikipedia.org/wiki/CAC_40", headers)]
        elif indice_scelto == "FTSE MIB (Italia)":
            tickers = [self.normalizza_ticker_europeo(t, ".MI") for t in self.estrai_ticker_wikipedia("https://en.wikipedia.org/wiki/FTSE_MIB", headers)]
        else:
            raise ValueError(f"Indice non riconosciuto: {indice_scelto}")
        return tickers

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
    # MOTORE FONDAMENTALI E CACHE
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
            entry = {
                "marketCap": mcap,
                "debtToEquity": info.get('debtToEquity', None),
                "freeCashflow": info.get('freeCashflow', None),
                "operatingMargins": info.get('operatingMargins', None),
                "returnOnEquity": info.get('returnOnEquity', None),
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
                "operatingMargins": None, "returnOnEquity": None, "last_updated": now.isoformat()
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

    def compute_poc(self, hist, start_idx, end_idx, n_bins=60):
        segment = hist.iloc[start_idx:end_idx]
        if len(segment) < 2:
            return None
        low = segment["Low"].to_numpy(dtype=float)
        high = segment["High"].to_numpy(dtype=float)
        volume = segment["Volume"].to_numpy(dtype=float)
        price_min = float(np.nanmin(low)); price_max = float(np.nanmax(high))
        if price_max <= price_min:
            return None
        bins = np.linspace(price_min, price_max, n_bins + 1)
        bin_centers = (bins[:-1] + bins[1:]) / 2
        bw = bins[1] - bins[0]
        bar_range = high - low
        valid = (bar_range > 0) & np.isfinite(bar_range) & np.isfinite(volume)
        if not valid.any():
            return None
        low = low[valid]; high = high[valid]; volume = volume[valid]; bar_range = bar_range[valid]
        b_lo = np.clip(np.searchsorted(bins, low, side='right') - 1, 0, n_bins - 1)
        b_hi = np.clip(np.searchsorted(bins, high, side='left') - 1, 0, n_bins - 1)
        acc = np.zeros(n_bins)
        same = (b_lo == b_hi)
        np.add.at(acc, b_lo[same], volume[same])
        multi = ~same
        if multi.any():
            lo = b_lo[multi]; hi = b_hi[multi]; vol_m = volume[multi]; rng_m = bar_range[multi]
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
        return float(bin_centers[poc_idx])

    def get_pocs_from_hist(self, hist, n_bins=60):
        if hist.empty or len(hist) < 10:
            return []
        structural_lows = self.find_structural_lows(hist)
        total_bars = len(hist)
        current_year = datetime.datetime.now().year
        pocs = []
        for bar_pos, low_price, drop, anchor_date in structural_lows:
            poc_price = self.compute_poc(hist, bar_pos, total_bars, n_bins=n_bins)
            if poc_price is None:
                continue
            years_ago = max(current_year - anchor_date.year, 0)
            age_weight = 1.0 + np.log1p(years_ago)
            drop_weight = 1.0 + (drop / 50.0)
            segment_bars = total_bars - bar_pos
            bar_weight = 1.0 + np.log1p(segment_bars / BARS_PER_YEAR)
            raw_weight = age_weight * drop_weight * bar_weight
            pocs.append({"anchor_year": int(anchor_date.year), "anchor_date": anchor_date, "drop_pct": round(float(drop), 1), "poc_price": round(float(poc_price), 4), "weight": float(raw_weight)})
        if pocs:
            max_w = max(p["weight"] for p in pocs); min_w = min(p["weight"] for p in pocs)
            for p in pocs:
                if max_w > min_w:
                    p["weight_norm"] = round(1 + 9 * (p["weight"] - min_w) / (max_w - min_w), 1)
                else:
                    p["weight_norm"] = 5.0
        return pocs

    def closest_poc(self, pocs, current_price, max_dist_pct=MAX_POC_DIST_PCT):
        if not pocs:
            return None, None
        best_poc = None; best_dist = None
        for poc in pocs:
            poc_price = float(poc["poc_price"])
            dist = (current_price - poc_price) / poc_price * 100
            if abs(dist) > max_dist_pct:
                continue
            if best_dist is None or abs(dist) < abs(best_dist):
                best_dist = dist; best_poc = poc
        if best_poc is None:
            return None, None
        return best_poc, round(float(best_dist), 2)

    def calcola_segnali_bottom(self, hist):
        if len(hist) < WIN_ROC + 5:
            return 0, "Dati insufficienti"
        close = hist['Close'].astype(float); volume = hist['Volume'].astype(float)
        score = 0; dettagli = []
        roc = close.pct_change(periods=WIN_ROC) * 100
        roc_current = roc.iloc[-1]
        roc_before = roc.iloc[-WIN_ROC_COMPARE] if len(roc) >= WIN_ROC_COMPARE else roc_current
        if not pd.isna(roc_current) and not pd.isna(roc_before) and roc_current > roc_before:
            score += 1; dettagli.append(f"Decelerazione (ROC: {roc_current:.1f}% > {roc_before:.1f}%)")
        exp1 = close.ewm(span=12, adjust=False).mean(); exp2 = close.ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2; signal = macd.ewm(span=9, adjust=False).mean(); histogram = macd - signal
        if len(histogram) >= 2 and histogram.iloc[-1] > histogram.iloc[-2]:
            score += 1; dettagli.append("MACD Histogram in risalita")
        try:
            pocs = self.get_pocs_from_hist(hist); vwap_info = self.compute_vwap_levels(hist)
            poc_op, dist_op = self.closest_poc(pocs, float(close.iloc[-1]))
            if poc_op is not None:
                wn = float(poc_op.get("weight_norm", 0.0))
                mom_up = close.iloc[-1] > close.iloc[-min(WIN_MOM, len(close) - 1)]
                if abs(dist_op) < 3 and wn >= MIN_POC_WEIGHT_NORM and mom_up:
                    score += 1; dettagli.append(f"Vicino al POC ({abs(dist_op):.1f}%)")
            if vwap_info["convergence_count"] >= 2:
                score += 1; dettagli.append(f"Convergenza VWAP ({vwap_info['convergence_label']})")
        except Exception:
            pass
        if len(volume) >= WIN_VOL + 1:
            vol_ultimo = volume.iloc[-1]; vol_media = volume.iloc[-(WIN_VOL + 1):-1].mean()
            if len(close) >= 3:
                force_index = (close.iloc[-1] - close.iloc[-2]) * volume.iloc[-1]
                force_prev = (close.iloc[-2] - close.iloc[-3]) * volume.iloc[-2]
                if vol_media > 0 and vol_ultimo > 1.3 * vol_media and force_index > force_prev:
                    score += 1; dettagli.append("Volume e Forza in aumento")
        return int(score), ", ".join(dettagli) if dettagli else "Nessun segnale"

    # ===============================
    # MOTORE DI SCREENING
    # ===============================
    def perform_screening(self, indice_scelto, min_market_cap, soglia_drawdown, soglia_poc_pct):
        self.add_debug(f"🚀 Avvio screening ottimizzato per {indice_scelto}...", "info")
        try:
            tickers = self.ottieni_tickers_indice(indice_scelto)
            self.add_debug(f"Trovati {len(tickers)} ticker su Wikipedia.", "info")
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
                    skip = True; break
            if t in problematic_tickers:
                skip = True
            if not skip:
                clean_tickers.append(t)
        self.add_debug(f"Ticker puliti per il download: {len(clean_tickers)}", "info")
        df_batch = self.download_prices_batch(clean_tickers)
        if df_batch.empty:
            self.add_debug("Nessun dato scaricato da yfinance. Verrà tentata l'analisi offline con la cache locale...", "warning")
        candidates = []; candidates_hist = {}
        self.add_debug("Calcolo drawdown e filtraggio preliminare...", "info")
        for ticker in clean_tickers:
            hist = self.get_ticker_history_from_batch(df_batch, ticker)
            if hist is None or len(hist) < 10:
                continue
            close_series = hist['Close'].dropna(); high_series = hist['High'].dropna()
            if close_series.empty or high_series.empty:
                continue
            price_now = float(close_series.values[-1]); ath_value = float(high_series.max())
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
            c_data = candidates_hist[ticker]; hist = c_data["hist"]; price_now = c_data["price_now"]; current_dd = c_data["current_dd"]
            poc_label, dist_label, alert_poc = "N/D", "N/D", ""
            try:
                pocs = self.get_pocs_from_hist(hist)
                poc_vicino, dist_poc_pct = self.closest_poc(pocs, price_now)
                if poc_vicino is not None:
                    poc_label = f"{poc_vicino['poc_price']:.2f} ({poc_vicino['anchor_year']})"
                    dist_label = f"{dist_poc_pct:+.1f}%"
                    wn_vicino = float(poc_vicino.get("weight_norm", 0.0))
                    alert_poc = "🎯 SU POC" if (abs(dist_poc_pct) <= soglia_poc_pct and wn_vicino >= MIN_POC_WEIGHT_NORM) else ""
            except Exception as e:
                self.add_debug(f"Errore calcolo POC per {ticker}: {e}", "warning")
            bottom_score, bottom_dettagli = self.calcola_segnali_bottom(hist)
            vwap_info = self.compute_vwap_levels(hist)
            pre_filtered.append({
                "Ticker": ticker, "Indice": indice_scelto, "Prezzo": round(price_now, 2),
                "Drawdown (%)": round(current_dd, 2), "Market Cap (B)": round(mcap / 1e9, 2) if mcap > 0 else 0.0,
                "POC più vicino": poc_label, "Distanza POC (%)": dist_label, "🎯 ALERT POC": alert_poc,
                "VWAP 4Y": vwap_info["vwap_4y"], "VWAP 1Y": vwap_info["vwap_1y"], "VWAP 3M": vwap_info["vwap_3m"],
                "Convergenza VWAP": vwap_info["convergence_label"],
                "Bottom Score (0-4)": bottom_score, "Bottom Dettagli": bottom_dettagli,
                "_debtToEquity": fund.get("debtToEquity", None), "_freeCashflow": fund.get("freeCashflow", None),
                "_operatingMargins": fund.get("operatingMargins", None), "_returnOnEquity": fund.get("returnOnEquity", None)
            })
        self.add_debug(f"Pre-filtrati rimasti dopo Market Cap: {len(pre_filtered)}", "info")
        if not pre_filtered:
            return [], []
        df_fund = pd.DataFrame(pre_filtered)
        med_debt = df_fund["_debtToEquity"].dropna().median() if not df_fund["_debtToEquity"].dropna().empty else 0.0
        med_fcf = df_fund["_freeCashflow"].dropna().median() if not df_fund["_freeCashflow"].dropna().empty else 0.0
        med_margin = df_fund["_operatingMargins"].dropna().median() if not df_fund["_operatingMargins"].dropna().empty else 0.0
        med_roe = df_fund["_returnOnEquity"].dropna().median() if not df_fund["_returnOnEquity"].dropna().empty else 0.0
        medians = {"debtToEquity": med_debt, "freeCashflow": med_fcf, "operatingMargins": med_margin, "returnOnEquity": med_roe}
        self.add_debug(f"Mediane calcolate per {indice_scelto}: {medians}", "info")
        macro_info = self.ottieni_bussola_argo(); argo_bussola = macro_info["bussola"]
        final_list = []; spostamenti_rilevati = []
        for item in pre_filtered:
            ticker = item["Ticker"]; score = 0
            d_eq = item["_debtToEquity"]; fcf = item["_freeCashflow"]; op_m = item["_operatingMargins"]; roe = item["_returnOnEquity"]
            if d_eq is not None and d_eq <= medians["debtToEquity"]:
                score += 1
            if fcf is not None and fcf >= medians["freeCashflow"]:
                score += 1
            if op_m is not None and op_m >= medians["operatingMargins"]:
                score += 1
            if roe is not None and roe >= medians["returnOnEquity"]:
                score += 1
            item["Quality Score (0-4)"] = int(score)
            mcap_val = item["Market Cap (B)"]
            base_size = 10.0 if mcap_val >= 10.0 else (5.0 if mcap_val >= 2.0 else 2.0)
            size_mult = 1.2 if score >= 3 else (1.0 if score >= 2 else 0.6)
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
            for temp_field in ["_debtToEquity", "_freeCashflow", "_operatingMargins", "_returnOnEquity"]:
                item.pop(temp_field, None)
            final_list.append(item)
        self.screener_database[indice_scelto] = final_list
        if "_last_scans" not in self.screener_database:
            self.screener_database["_last_scans"] = {}
        self.screener_database["_last_scans"][indice_scelto] = datetime.datetime.now().isoformat()
        self.save_all()
        self.add_debug(f"✅ Screening completato per {indice_scelto}. {len(final_list)} titoli registrati.", "success")
        return final_list, spostamenti_rilevati
