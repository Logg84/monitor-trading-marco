"""
Data engine: prezzi, indicatori, Health Check, ZONE VOLUMETRICHE multiple
(soglia adattiva + larghezza max = min(15% range, 8×ATR20)),
VWAP ancorati, Bottom Score, REVERSAL STATE (punti 🟡/🟢), trimestrali,
cache screening, universo, risoluzione ticker.
Solo letture, mai decisioni.
"""
from __future__ import annotations
import datetime as _dt
import json
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INDICES_DIR = DATA_DIR / "indices"
SCREENING_CACHE_CSV = DATA_DIR / "screening_latest.csv"
SCREENING_CACHE_META = DATA_DIR / "screening_meta.json"

DEFAULT_SAMPLE = {
    "SP500_SAMPLE": ["AAPL", "MSFT", "NVDA", "JNJ", "PG", "KO", "XOM", "HD", "V", "UNH"],
    "EURO_SAMPLE": ["ASML.AS", "SAP.DE", "TTE.PA", "SAN.MC", "ENI.MI", "UCG.MI"],
}

# ── Prezzi ─────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def get_prices(ticker: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
    df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=True)
    if df.empty:
        raise ValueError(f"Nessun dato per {ticker}")
    df.index = pd.to_datetime(df.index)
    df = df[["Open", "High", "Low", "Close", "Volume"]]
    df = df.dropna(subset=["Close"])
    if df.empty:
        raise ValueError(f"Nessun dato valido per {ticker}")
    return df

@st.cache_data(ttl=6 * 3600, show_spinner=False)
def get_prices_long(ticker: str) -> pd.DataFrame:
    df = yf.Ticker(ticker).history(period="max", interval="1wk", auto_adjust=True)
    if df.empty:
        raise ValueError(f"Nessun dato lungo per {ticker}")
    df.index = pd.to_datetime(df.index)
    df = df[["High", "Low", "Close", "Volume"]]
    df = df.dropna(subset=["Close"])
    if df.empty:
        raise ValueError(f"Nessun dato lungo valido per {ticker}")
    return df

@st.cache_data(ttl=3600, show_spinner=False)
def download_closes_chunked(tickers: tuple, period: str = "2y",
                            chunk_size: int = 100) -> pd.DataFrame:
    tk = list(tickers)
    frames = []
    for i in range(0, len(tk), chunk_size):
        block = tk[i:i + chunk_size]
        try:
            raw = yf.download(block, period=period, interval="1d",
                              auto_adjust=True, progress=False, threads=True)
        except Exception:
            continue
        if raw is None or raw.empty:
            continue
        if not isinstance(raw.columns, pd.MultiIndex):
            t0 = block[0]
            raw = pd.DataFrame({("Close", t0): raw["Close"],
                                ("Volume", t0): raw["Volume"]})
        frames.append(raw[["Close", "Volume"]])
    if not frames:
        raise ValueError("Download multiplo fallito")
    return pd.concat(frames, axis=1)

@st.cache_data(ttl=6 * 3600, show_spinner=False)
def download_weekly_chunked(tickers: tuple, chunk_size: int = 100) -> pd.DataFrame:
    tk = list(tickers)
    frames = []
    for i in range(0, len(tk), chunk_size):
        block = tk[i:i + chunk_size]
        try:
            raw = yf.download(block, period="max", interval="1wk",
                              auto_adjust=True, progress=False, threads=True)
        except Exception:
            continue
        if raw is None or raw.empty:
            continue
        if not isinstance(raw.columns, pd.MultiIndex):
            t0 = block[0]
            raw = pd.DataFrame({("Close", t0): raw["Close"],
                                ("Volume", t0): raw["Volume"],
                                ("High", t0): raw["High"],
                                ("Low", t0): raw["Low"]})
        frames.append(raw[["High", "Low", "Close", "Volume"]])
    if not frames:
        raise ValueError("Download settimanale fallito")
    return pd.concat(frames, axis=1)

# ── Indicatori ─────────────────────────────────────────────
def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def atr(df: pd.DataFrame, period: int = 20) -> float:
    prev = df["Close"].shift(1)
    tr = pd.concat([df["High"] - df["Low"],
                    (df["High"] - prev).abs(),
                    (df["Low"] - prev).abs()], axis=1).max(axis=1)
    val = float(tr.rolling(period).mean().iloc[-1])
    return 0.0 if np.isnan(val) else val

def vwap_anchored(df: pd.DataFrame, lookback: int = 60) -> float:
    w = df.tail(lookback)
    typical = (w["High"] + w["Low"] + w["Close"]) / 3
    vol = w["Volume"].replace(0, np.nan)
    val = float((typical * vol).sum() / vol.sum())
    return float(w["Close"].iloc[-1]) if np.isnan(val) else val

# ── Zone volumetriche multiple ─────────────────────────────
def _split_run(vps: np.ndarray, l: int, h: int, max_bins: int) -> list[tuple[int, int]]:
    segs = []
    stack = [(l, h)]
    while stack:
        l, h = stack.pop()
        w = h - l + 1
        if w <= max_bins or w < 6:
            segs.append((l, h))
            continue
        inner = vps[l + 1:h]
        if inner.size == 0:
            segs.append((l, h))
            continue
        m = l + 1 + int(np.argmin(inner))
        stack.append((l, m))
        stack.append((m, h))
    return segs

def volume_zones(wdf: pd.DataFrame, bins: int = 120, max_zones: int = 5,
                 half_life_years: float = 4.0, min_share: float = 0.02,
                 max_width_frac: float = 0.15, atr20: float | None = None,
                 atr_width_mult: float = 8.0) -> list[dict]:
    if wdf is None or len(wdf) < 40:
        return []
    close = wdf["Close"]
    vol = wdf["Volume"].fillna(0)
    total_vol = float(vol.sum())
    if total_vol <= 0:
        return []
    age = ((wdf.index[-1] - wdf.index).days / 365.25).to_numpy()
    pmin, pmax = float(close.min()), float(close.max())
    if pmax <= pmin:
        return []
    price_bins = np.linspace(pmin, pmax, bins + 1)
    bin_w = (pmax - pmin) / bins
    idx = np.clip(np.searchsorted(price_bins, close.to_numpy(), side="right") - 1,
                  0, bins - 1)
    v = vol.to_numpy()
    vp = np.bincount(idx, weights=v, minlength=bins).astype(float)
    va = np.bincount(idx, weights=v * age, minlength=bins).astype(float)
    vps = np.convolve(vp, np.array([0.25, 0.5, 0.25]), mode="same")
    pos = vps[vps > 0]
    if pos.size == 0:
        return []
    thr = float(np.percentile(pos, 70))
    max_width_price = max_width_frac * (pmax - pmin)
    if atr20 is not None and atr20 > 0:
        max_width_price = min(max_width_price, atr_width_mult * atr20)
    max_bins = max(4, int(max_width_price / bin_w))

    above = vps >= thr
    zones = []
    i = 0
    while i < bins:
        if above[i]:
            j = i
            while j + 1 < bins and above[j + 1]:
                j += 1
            for (l, h) in _split_run(vps, i, j, max_bins):
                zv = float(vp[l:h + 1].sum())
                share = zv / total_vol
                if share < min_share:
                    continue
                zage = float(va[l:h + 1].sum() / zv) if zv > 0 else float(age[-1])
                zones.append({"lo": float(price_bins[l]), "hi": float(price_bins[h + 1]),
                              "center": float((price_bins[l] + price_bins[h + 1]) / 2),
                              "share": share, "age": zage})
            i = j + 1
        else:
            i += 1
    if not zones:
        return []
    mx = max(z["share"] for z in zones)
    for z in zones:
        rec = float(np.exp(-z["age"] / half_life_years))
        z["recency"] = rec
        z["score"] = int(round(100 * (0.6 * (z["share"] / mx) + 0.4 * rec)))
    zones.sort(key=lambda z: -z["score"])
    return zones[:max_zones]

def zone_component(price: float, zones: list[dict], atr20: float) -> float:
    if not zones or atr20 <= 0:
        return 50.0
    best = None
    for z in zones:
        w = z["score"] / 100.0
        if z["lo"] <= price <= z["hi"]:
            cand = 70 + 30 * w
        else:
            d = min(abs(price - z["lo"]), abs(price - z["hi"])) / atr20
            cand = max(0.0, 70 - d * 15) * (0.5 + 0.5 * w)
        best = cand if best is None else max(best, cand)
    return float(np.clip(best, 0, 100))

# ── VWAP ancorati a minimi strutturali ─────────────────────
def anchored_vwap_from(wdf: pd.DataFrame, i: int) -> float:
    w = wdf.iloc[i:]
    typical = (w["High"] + w["Low"] + w["Close"]) / 3
    vol = w["Volume"].replace(0, np.nan)
    val = float((typical * vol).sum() / vol.sum())
    return float(w["Close"].iloc[-1]) if np.isnan(val) else val

def structural_anchors(wdf: pd.DataFrame, k: int = 13, min_gap_weeks: int = 26,
                       max_n: int = 3, earnings: list | None = None) -> list[dict]:
    n = len(wdf)
    if n < 3 * k or not {"High", "Low"}.issubset(wdf.columns):
        return []
    low, high = wdf["Low"], wdf["High"]
    roll = low.rolling(2 * k + 1, center=True, min_periods=2 * k + 1).min()
    mask = (low <= roll + 1e-12) & roll.notna()
    fut_max = high.iloc[::-1].rolling(2 * k, min_periods=k).max().iloc[::-1]
    rise = (fut_max / low - 1) * 100
    cand = []
    for i in np.flatnonzero(mask.to_numpy()):
        r_ = rise.iloc[i]
        if np.isnan(r_) or r_ <= 0:
            continue
        near = False
        if earnings:
            d = wdf.index[i]
            near = any(abs((d - e).days) <= 30 for e in earnings)
        cand.append((float(r_) * (1.25 if near else 1.0), int(i), bool(near)))
    cand.sort(key=lambda x: -x[0])
    chosen = []
    for sel, i, near in cand:
        if all(abs(i - c["i"]) >= min_gap_weeks for c in chosen):
            chosen.append({"i": i, "date": wdf.index[i], "price": float(low.iloc[i]),
                           "near": near, "rise": float(rise.iloc[i])})
        if len(chosen) >= max_n:
            break
    chosen.sort(key=lambda z: z["date"], reverse=True)
    out = []
    for n_i, z in enumerate(chosen, 1):
        z = dict(z)
        z["label"] = f"VWA{n_i}"
        z["vwap"] = anchored_vwap_from(wdf, z["i"])
        out.append(z)
    return out

# ── Health Check ───────────────────────────────────────────
@st.cache_data(ttl=86400, show_spinner=False)
def get_info(ticker: str) -> dict:
    try:
        return yf.Ticker(ticker).info or {}
    except Exception:
        return {}

def company_name(ticker: str) -> str:
    info = get_info(ticker)
    return str(info.get("longName") or info.get("shortName") or "—")

def health_check(ticker: str) -> dict:
    info = get_info(ticker)
    checks = []

    def add(name, ok, detail):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    roe = info.get("returnOnEquity")
    add("ROE ≥ 15%", roe is not None and roe >= 0.15, f"{roe:.1%}" if roe is not None else "n/d")
    de = info.get("debtToEquity")
    add("D/E ≤ 100", de is not None and de <= 100, f"{de:.0f}" if de is not None else "n/d")
    om = info.get("operatingMargins")
    add("Margine operativo ≥ 10%", om is not None and om >= 0.10, f"{om:.1%}" if om is not None else "n/d")
    rg = info.get("revenueGrowth")
    add("Crescita ricavi > 0", rg is not None and rg > 0, f"{rg:.1%}" if rg is not None else "n/d")
    fc = info.get("freeCashflow")
    add("FCF positivo", fc is not None and fc > 0, f"{fc/1e9:.1f}B" if fc is not None else "n/d")
    score = int(round(100 * sum(c["ok"] for c in checks) / len(checks)))
    return {"ticker": ticker, "score": score, "checks": checks}

# ── Bottom Score ───────────────────────────────────────────
def bottom_score(df: pd.DataFrame, zones: list[dict] | None = None) -> dict:
    close = df["Close"].dropna()
    if len(close) < 30:
        return {"score": 0, "drawdown": 0.0, "rsi": 50.0, "roc10": 0.0, "decel": 0.0,
                "components": {"drawdown": 0.0, "rsi": 50.0, "zone": 50.0, "decel": 50.0}}
    price = float(close.iloc[-1])
    ath = float(close.max())
    drawdown = (price / ath - 1) * 100.0
    r = float(rsi(close).iloc[-1])
    if np.isnan(r):
        r = 50.0
    a = atr(df)
    roc = close.pct_change(10) * 100
    roc_now = float(roc.iloc[-1]) if not np.isnan(roc.iloc[-1]) else 0.0
    roc_prev = float(roc.iloc[-11]) if len(roc) > 11 and not np.isnan(roc.iloc[-11]) else roc_now
    decel = roc_now - roc_prev
    dd_c = float(np.clip(-drawdown / 0.6, 0, 100))
    rsi_c = float(np.clip((70 - r) / 0.4, 0, 100))
    zone_c = zone_component(price, zones or [], a)
    decel_c = float(np.clip(50 + decel * 5, 0, 100))
    components = {"drawdown": dd_c, "rsi": rsi_c, "zone": zone_c, "decel": decel_c}
    components = {k: (0.0 if np.isnan(v) else float(v)) for k, v in components.items()}
    total = (0.4 * components["drawdown"] + 0.2 * components["rsi"] +
             0.2 * components["zone"] + 0.2 * components["decel"])
    return {"score": int(round(float(np.nan_to_num(total)))), "drawdown": drawdown,
            "rsi": r, "roc10": roc_now, "decel": decel, "components": components}

# ── REVERSAL STATE (punti 🟡/) ────────────────────────────
def _cross_recent(above: np.ndarray, lookback: int = 5) -> bool:
    n = len(above)
    if n < 2:
        return False
    return any(bool(above[-i]) and not bool(above[-i - 1])
               for i in range(1, min(lookback, n - 1) + 1))

def _weekly_d3(wdf: pd.DataFrame) -> bool:
    if wdf is None or len(wdf) < 3:
        return False
    low_w = wdf["Low"]
    close_w = wdf["Close"]
    return bool(low_w.iloc[-1] > low_w.iloc[-2] and close_w.iloc[-2] < close_w.iloc[-3])

def _d12(df: pd.DataFrame, i: int) -> tuple[bool, bool]:
    close = df["Close"]
    if i < 1:
        return False, False
    sub = df.iloc[:i + 1]
    price = float(close.iloc[i])
    vwap60 = vwap_anchored(sub)
    d1 = bool(price > vwap60 and _cross_recent((close.iloc[:i + 1] > vwap60).to_numpy()))
    hi_prev = float(df["High"].iloc[max(0, i - 20):i].max())
    d2 = bool(price > hi_prev)
    return d1, d2

def reversal_state(df: pd.DataFrame, wdf: pd.DataFrame, zones: list[dict],
                   anchors: list[dict], hc_score: int,
                   es_positive: bool | None = None) -> dict:
    """
    Punteggio reversal (A = cancello DD ≤ −20%):
    B decel>0 =1 · C confluenza =1 · G chiusura fresca sopra SMA20 =2 ·
    D conferma (D1/D2/D3) =1 · E qualità+persistenza =1. Max 6.
    🟡 = A + punti ≥2 (G da sola basta; B+C insieme bastano).
    🟢 = A + punti ≥5 + D (senza G non si arriva: è il suo valore doppio).
    """
    close = df["Close"]
    if len(close) < 30:
        return {"dd": 0.0, "points": 0, "kind": None,
                "flags": {"B": False, "C": False, "G": False, "D": False, "E": False}}
    price = float(close.iloc[-1])
    dd = (price / float(close.max()) - 1) * 100
    roc = close.pct_change(10) * 100
    decel = float(roc.iloc[-1] - roc.iloc[-11]) if len(roc) > 11 else 0.0
    B = bool(decel > 0)

    a20 = atr(df)
    in_zone, zscore = False, 0
    for z in zones:
        if z["lo"] <= price <= z["hi"]:
            in_zone = True
            zscore = max(zscore, z["score"])
    near_vwa = any(abs(price - an["vwap"]) <= a20 for an in anchors) if anchors else False
    C = bool((in_zone and zscore >= 50) or near_vwa)

    ma = close.rolling(20).mean()
    above = (close > ma).to_numpy()
    G = bool(above[-1] and _cross_recent(above))

    d1, d2 = _d12(df, len(close) - 1)
    d3 = _weekly_d3(wdf)
    D = bool(d1 or d2 or d3)

    qual = bool(hc_score >= 40) and (es_positive is not False)
    d1p, d2p = _d12(df, len(close) - 2)
    persist = bool(d3 or ((d1 or d2) and (d1p or d2p or d3)))
    E = bool(qual and persist)

    points = int(B) + int(C) + 2 * int(G) + int(D) + int(E)
    kind = None
    if dd <= -20:
        if points >= 5 and D:
            kind = "🟢"
        elif points >= 2:
            kind = "🟡"
    return {"dd": dd, "points": points, "kind": kind,
            "flags": {"B": B, "C": C, "G": G, "D": D, "E": E}}

def candidate_at(df: pd.DataFrame, zones: list[dict], anchors: list[dict],
                 i: int, D: bool, E: bool) -> tuple[float, int]:
    """DD e punti approssimati alla posizione i (per pruning a 5 chiusure)."""
    close = df["Close"]
    c = close.iloc[:i + 1]
    price = float(c.iloc[-1])
    dd = (price / float(c.max()) - 1) * 100
    roc = c.pct_change(10) * 100
    decel = float(roc.iloc[-1] - roc.iloc[-11]) if len(roc) > 11 else 0.0
    B = bool(decel > 0)
    in_zone, zscore = False, 0
    for z in zones:
        if z["lo"] <= price <= z["hi"]:
            in_zone = True
            zscore = max(zscore, z["score"])
    a20 = atr(df)
    near_vwa = any(abs(price - an["vwap"]) <= a20 for an in anchors) if anchors else False
    C = bool((in_zone and zscore >= 50) or near_vwa)
    ma = c.rolling(20).mean()
    above = (c > ma).to_numpy()
    G = bool(above[-1] and _cross_recent(above))
    points = int(B) + int(C) + 2 * int(G) + int(D) + int(E)
    return dd, points

# ── Trimestrali ────────────────────────────────────────────
@st.cache_data(ttl=86400, show_spinner=False)
def earnings_dates_list(ticker: str) -> list:
    try:
        ed = yf.Ticker(ticker).earnings_dates
        if ed is not None and not ed.empty:
            return [pd.Timestamp(x) for x in ed.index]
    except Exception:
        pass
    return []

@st.cache_data(ttl=86400, show_spinner=False)
def earnings_snapshot(ticker: str) -> dict:
    out = {"positive": None, "surprise": None, "date": None, "rev_yoy": None, "quarters": None}
    t = yf.Ticker(ticker)
    try:
        ed = t.earnings_dates
        if ed is not None and not ed.empty and "Reported EPS" in ed.columns:
            reported = ed[ed["Reported EPS"].notna()]
            if not reported.empty:
                last = reported.iloc[-1]
                sur = last.get("Surprise %")
                out["date"] = str(reported.index[-1].date())
                if sur is not None and not np.isnan(float(sur)):
                    out["surprise"] = float(sur)
                    out["positive"] = out["surprise"] > 0
    except Exception:
        pass
    try:
        qf = t.quarterly_financials
        if qf is not None and not qf.empty and "Total Revenue" in qf.index:
            rev = qf.loc["Total Revenue"].dropna().sort_index()
            if len(rev) >= 2:
                out["quarters"] = rev
                if len(rev) >= 5:
                    lv, pv = float(rev.iloc[-1]), float(rev.iloc[-5])
                    if pv:
                        out["rev_yoy"] = (lv / pv - 1) * 100
    except Exception:
        pass
    if out["positive"] is None and out["rev_yoy"] is not None:
        out["positive"] = out["rev_yoy"] > 0
    return out

# ── Cache screening ────────────────────────────────────────
def save_screening_cache(df: pd.DataFrame, meta: dict) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(SCREENING_CACHE_CSV, index=False)
        meta = dict(meta)
        meta["saved_at"] = _dt.datetime.now().isoformat(timespec="seconds")
        SCREENING_CACHE_META.write_text(json.dumps(meta, ensure_ascii=False))
    except Exception:
        pass

def load_screening_cache() -> tuple[pd.DataFrame | None, dict]:
    try:
        if not SCREENING_CACHE_CSV.exists():
            return None, {}
        df = pd.read_csv(SCREENING_CACHE_CSV)
        meta = {}
        if SCREENING_CACHE_META.exists():
            meta = json.loads(SCREENING_CACHE_META.read_text())
        if df.empty:
            return None, meta
        return df, meta
    except Exception:
        return None, {}

# ── Indici & screening ─────────────────────────────────────
@st.cache_data(ttl=86400, show_spinner=False)
def load_index_constituents(name: str) -> list[str]:
    path = INDICES_DIR / f"{name}.csv"
    if path.exists():
        try:
            if path.stat().st_size < 10:
                raise ValueError(f"file vuoto: {path.name}")
            df = pd.read_csv(path)
        except Exception as e:
            st.warning(f"File indice {name} non leggibile ({e}). Rigenera con scripts/download_indices.py --force")
            df = None
        if df is not None and not df.empty:
            col = "Ticker" if "Ticker" in df.columns else df.columns[0]
            out = [str(t).strip() for t in df[col].dropna().tolist()]
            out = [t for t in out if t and t.lower() != "nan"]
            if out:
                return out
    return list(DEFAULT_SAMPLE.get(name, []))

def _weekly_for(data_w, t, sub):
    if data_w is not None:
        try:
            cw = data_w["Close"][t].dropna()
            vw = data_w["Volume"][t].dropna()
            hw = data_w["High"][t].reindex(cw.index)
            lw = data_w["Low"][t].reindex(cw.index)
            wdf = pd.DataFrame({"High": hw, "Low": lw, "Close": cw,
                                "Volume": vw.reindex(cw.index)}).dropna()
            if len(wdf) >= 40:
                return wdf
        except Exception:
            pass
    return sub

def screening(tickers: list[str], log=None) -> tuple[pd.DataFrame, dict]:
    def _log(msg):
        if log is not None:
            try:
                log(msg)
            except Exception:
                pass

    total = len(tickers)
    if total == 0:
        return pd.DataFrame(), {"total": 0, "valid": 0, "discarded": 0}
    _log(f"Ticker richiesti: {total}")
    _log("Download daily a blocchi (cache 1h)…")
    try:
        data = download_closes_chunked(tuple(tickers))
    except Exception:
        _log("Download daily fallito.")
        return pd.DataFrame(), {"total": total, "valid": 0, "discarded": total}
    _log("Download settimanale lungo a blocchi (cache 6h)…")
    try:
        data_w = download_weekly_chunked(tuple(tickers))
    except Exception:
        data_w = None
        _log("Settimanale non disponibile: zone su daily 2y.")
    _log("Elaborazione: zone, VWAP ancorati, reversal state, health…")
    rows = []
    for i, t in enumerate(tickers):
        if i and i % 100 == 0:
            _log(f"… elaborati {i}/{total}")
        try:
            c = data["Close"][t].dropna()
            v = data["Volume"][t].dropna()
            if len(c) < 80:
                continue
            sub = pd.DataFrame({"Close": c})
            sub["High"] = sub["Close"]
            sub["Low"] = sub["Close"]
            sub["Volume"] = v.reindex(c.index)
            price = float(c.iloc[-1])
            vwap60 = vwap_anchored(sub)
            a20 = atr(sub)
            wdf = _weekly_for(data_w, t, sub)
            zones = volume_zones(wdf, atr20=a20)
            anchors = structural_anchors(wdf)
            bs = bottom_score(sub, zones=zones)
            hc = health_check(t)
            rev = reversal_state(sub, wdf, zones, anchors, hc["score"])
            z1 = zones[0] if zones else None
            z2 = zones[1] if len(zones) > 1 else None
            in_lbl = ""
            for zi, z in enumerate(zones, 1):
                if z["lo"] <= price <= z["hi"]:
                    in_lbl = f"Z{zi}"
                    break
            vwa1 = anchors[0]["vwap"] if anchors else None
            rows.append({
                "Ticker": t, "Nome": company_name(t), "Prezzo": round(price, 2),
                "DD%": round(bs["drawdown"], 1), "RSI": round(bs["rsi"], 0),
                "VWAP60": round(vwap60, 2),
                "VWA1": round(vwa1, 2) if vwa1 else None,
                "VWA2": round(anchors[1]["vwap"], 2) if len(anchors) > 1 else None,
                "VWA3": round(anchors[2]["vwap"], 2) if len(anchors) > 2 else None,
                "Z1": (f"{z1['lo']:.2f}–{z1['hi']:.2f} ·{z1['score']}") if z1 else "—",
                "Z2": (f"{z2['lo']:.2f}–{z2['hi']:.2f} ·{z2['score']}") if z2 else "—",
                "Z1c": round(z1["center"], 4) if z1 else None,
                "In zona": in_lbl,
                "Segnale": f"{rev['kind']} {rev['points']}/6" if rev["kind"] else "—",
                "Health": hc["score"], "Bottom": bs["score"],
            })
        except Exception:
            continue
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("Bottom", ascending=False).reset_index(drop=True)
    diagnostics = {"total": total, "valid": len(rows), "discarded": total - len(rows)}
    _log(f"Completato: {len(rows)} validi, {total - len(rows)} scartati.")
    return out, diagnostics

# ── Universo & risoluzione ticker ──────────────────────────
SUFFIXES = ["", ".MI", ".PA", ".DE", ".MC", ".AS", ".L", ".SW", ".ST", ".BR"]

@st.cache_data(ttl=3600, show_spinner=False)
def build_universe() -> list[str]:
    tickers = set()
    for name in DEFAULT_SAMPLE:
        tickers.update(DEFAULT_SAMPLE[name])
    if INDICES_DIR.exists():
        for p in INDICES_DIR.glob("*.csv"):
            try:
                df = pd.read_csv(p)
                col = "Ticker" if "Ticker" in df.columns else df.columns[0]
                tickers.update(str(t).strip() for t in df[col])
            except Exception:
                continue
    return sorted(tickers)

@st.cache_data(ttl=7 * 86400, show_spinner=False)
def resolve_ticker(raw: str) -> str | None:
    raw = raw.strip().upper()
    if not raw:
        return None
    candidates = [raw] if "." in raw else [raw + s for s in SUFFIXES]
    for c in candidates:
        try:
            df = yf.Ticker(c).history(period="5d", auto_adjust=True)
            if not df.empty:
                return c
        except Exception:
            continue
    return None
