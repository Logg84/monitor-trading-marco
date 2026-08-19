"""
Data engine: prezzi, indicatori, Health Check, POC (volume profile),
VWAP, Bottom Score, universo, risoluzione ticker.
Ogni funzione è pura e cachata; nessuna decisione, solo letture.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INDICES_DIR = DATA_DIR / "indices"

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

@st.cache_data(ttl=3600, show_spinner=False)
def download_closes(tickers: tuple, period: str = "2y") -> pd.DataFrame:
    """Un solo download per tutti i titoli (Close + Volume)."""
    raw = yf.download(list(tickers), period=period, interval="1d",
                      auto_adjust=True, progress=False, threads=True)
    if raw.empty:
        raise ValueError("Download multiplo fallito")
    return raw[["Close", "Volume"]]

# ── Indicatori ─────────────────────────────────────────────
def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def atr(df: pd.DataFrame, period: int = 20) -> float:
    prev = df["Close"].shift(1)
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev).abs(),
        (df["Low"] - prev).abs(),
    ], axis=1).max(axis=1)
    val = float(tr.rolling(period).mean().iloc[-1])
    return 0.0 if np.isnan(val) else val

def vwap_anchored(df: pd.DataFrame, lookback: int = 60) -> float:
    w = df.tail(lookback)
    typical = (w["High"] + w["Low"] + w["Close"]) / 3
    vol = w["Volume"].replace(0, np.nan)
    val = float((typical * vol).sum() / vol.sum())
    return float(w["Close"].iloc[-1]) if np.isnan(val) else val

def poc_zone(poc: float, atr20: float, f: float = 0.6) -> tuple[float, float]:
    """Zona POC dinamica: ± f · ATR(20)."""
    half = atr20 * f
    return (poc - half, poc + half)

# ── Volume Profile ─────────────────────────────────────────
def volume_profile(df: pd.DataFrame, bins: int = 50) -> dict:
    close = df["Close"]
    vol = df["Volume"].fillna(0)
    price_min, price_max = float(close.min()), float(close.max())
    price_bins = np.linspace(price_min, price_max, bins + 1)
    vol_profile = np.zeros(bins)
    prices = close.to_numpy()
    volumes = vol.to_numpy()
    idx = np.clip(np.searchsorted(price_bins, prices, side="right") - 1, 0, bins - 1)
    for i in range(bins):
        vol_profile[i] = float(np.nansum(volumes[idx == i]))
    if vol_profile.sum() == 0:
        return {"poc": float(close.iloc[-1]), "hvn": [], "lvn": [],
                "profile": vol_profile, "bins": price_bins}
    poc_idx = int(np.argmax(vol_profile))
    poc_price = float((price_bins[poc_idx] + price_bins[poc_idx + 1]) / 2)
    threshold_high = np.percentile(vol_profile, 75)
    threshold_low = np.percentile(vol_profile, 25)
    hvn = [(float(price_bins[i]), float(price_bins[i + 1]))
           for i, v in enumerate(vol_profile) if v >= threshold_high]
    lvn = [(float(price_bins[i]), float(price_bins[i + 1]))
           for i, v in enumerate(vol_profile) if 0 < v <= threshold_low]
    return {"poc": poc_price, "hvn": hvn, "lvn": lvn,
            "profile": vol_profile, "bins": price_bins}

def poc_zone_from_profile(df: pd.DataFrame, f: float = 0.6) -> tuple[float, float, float]:
    vp = volume_profile(df)
    poc = vp["poc"]
    lo, hi = poc_zone(poc, atr(df), f)
    return poc, lo, hi

# ── Health Check (qualità) ─────────────────────────────────
@st.cache_data(ttl=86400, show_spinner=False)
def get_info(ticker: str) -> dict:
    try:
        return yf.Ticker(ticker).info or {}
    except Exception:
        return {}

def health_check(ticker: str) -> dict:
    info = get_info(ticker)
    checks = []
    
    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
    
    roe = info.get("returnOnEquity")
    add("ROE ≥ 15%", roe is not None and roe >= 0.15,
        f"{roe:.1%}" if roe is not None else "n/d")
    
    de = info.get("debtToEquity")
    add("D/E ≤ 100", de is not None and de <= 100,
        f"{de:.0f}" if de is not None else "n/d")
    
    om = info.get("operatingMargins")
    add("Margine operativo ≥ 10%", om is not None and om >= 0.10,
        f"{om:.1%}" if om is not None else "n/d")
    
    rg = info.get("revenueGrowth")
    add("Crescita ricavi > 0", rg is not None and rg > 0,
        f"{rg:.1%}" if rg is not None else "n/d")
    
    fc = info.get("freeCashflow")
    add("FCF positivo", fc is not None and fc > 0,
        f"{fc/1e9:.1f}B" if fc is not None else "n/d")
    
    score = int(round(100 * sum(c["ok"] for c in checks) / len(checks)))
    return {"ticker": ticker, "score": score, "checks": checks}

# ── Bottom Score (sconto + decelerazione) — NaN-safe ───────
def bottom_score(df: pd.DataFrame, poc: float | None = None, f: float = 0.6) -> dict:
    close = df["Close"].dropna()
    if len(close) < 30:
        return {"score": 0, "drawdown": 0.0, "rsi": 50.0, "roc10": 0.0,
                "decel": 0.0,
                "components": {"drawdown": 0.0, "rsi": 50.0,
                               "poc": 50.0, "decel": 50.0}}
    
    price = float(close.iloc[-1])
    ath = float(close.max())
    drawdown = (price / ath - 1) * 100.0
    
    r = float(rsi(close).iloc[-1])
    if np.isnan(r):
        r = 50.0
    
    a = atr(df)
    roc = close.pct_change(10) * 100
    roc_now = float(roc.iloc[-1])
    if np.isnan(roc_now):
        roc_now = 0.0
    
    roc_prev = float(roc.iloc[-11]) if len(roc) > 11 else roc_now
    if np.isnan(roc_prev):
        roc_prev = roc_now
    
    decel = roc_now - roc_prev
    
    dd_c = float(np.clip(-drawdown / 0.6, 0, 100))
    rsi_c = float(np.clip((70 - r) / 0.4, 0, 100))
    
    if poc is not None and a > 0:
        lo, hi = poc_zone(poc, a, f)
        if lo <= price <= hi:
            poc_c = 100.0
        else:
            dist = min(abs(price - lo), abs(price - hi)) / a
            poc_c = float(np.clip(100 - dist * 25, 0, 100))
    else:
        poc_c = 50.0
    
    decel_c = float(np.clip(50 + decel * 5, 0, 100))
    
    components = {"drawdown": dd_c, "rsi": rsi_c, "poc": poc_c, "decel": decel_c}
    components = {k: (0.0 if np.isnan(v) else float(v))
                  for k, v in components.items()}
    
    total = (0.4 * components["drawdown"] + 0.2 * components["rsi"] +
             0.2 * components["poc"] + 0.2 * components["decel"])
    score = int(round(float(np.nan_to_num(total))))
    
    return {"score": score, "drawdown": drawdown, "rsi": r,
            "roc10": roc_now, "decel": decel, "components": components}

# ── Indici & screening ─────────────────────────────────────
@st.cache_data(ttl=86400, show_spinner=False)
def load_index_constituents(name: str) -> list[str]:
    path = INDICES_DIR / f"{name}.csv"
    if path.exists():
        df = pd.read_csv(path)
        col = "Ticker" if "Ticker" in df.columns else df.columns[0]
        return [str(t).strip() for t in df[col].tolist()]
    return DEFAULT_SAMPLE.get(name, [])

def screening(tickers: list[str]) -> tuple[pd.DataFrame, dict]:
    """
    Esegue screening su una lista di ticker.
    
    Returns:
        tuple: (DataFrame con risultati, dict con diagnostica)
    """
    total_tickers = len(tickers)
    
    try:
        data = download_closes(tuple(tickers))
    except Exception:
        return pd.DataFrame(), {"total": total_tickers, "valid": 0, "discarded": total_tickers}
    
    rows = []
    valid_count = 0
    
    for t in tickers:
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
            vwap = vwap_anchored(sub)
            bs = bottom_score(sub, poc=vwap)
            hc = health_check(t)
            
            rows.append({
                "Ticker": t,
                "Prezzo": round(price, 2),
                "DD%": round(bs["drawdown"], 1),
                "RSI": round(bs["rsi"], 0),
                "VWAP60": round(vwap, 2),
                "Health": hc["score"],
                "Bottom": bs["score"],
            })
            valid_count += 1
        except Exception:
            continue
    
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("Bottom", ascending=False).reset_index(drop=True)
    
    diagnostics = {
        "total": total_tickers,
        "valid": valid_count,
        "discarded": total_tickers - valid_count
    }
    
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
