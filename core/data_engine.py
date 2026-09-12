"""
Data engine: prezzi, indicatori, Health Check, ZONE VOLUMETRICHE multiple (soglia adattiva + larghezza max = min(15% range, 8×ATR20)), VWAP ancorati a minimi strutturali, Bottom Score, REVERSAL STATE (punti 🟡/🟢) con bypass Sifrediana istantaneo, trimestrali, cache screening, universo, risoluzione ticker, link TradingView, sanitizzazione ticker indici (regex + mappa anti doppio-suffisso), CONTESTO DI SETTORE (core/sectors.py: etichetta, stato 0-100, breadth EW−CW, Priorità — puramente informativo: non entra in reversal_state né nelle regole di uscita). Ogni funzione è pura e cachata; nessuna decisione, solo letture.
"""

from __future__ import annotations
import datetime as _dt
import json
import re
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
from core.wyckoff import wyckoff_analysis
from core.sectors import (bonus_sector, sector_cell, sector_label, sector_of, sector_rows, sub_of, sub_rows, vento)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INDICES_DIR = DATA_DIR / "indices"
SCREENING_CACHE_CSV = DATA_DIR / "screening_latest.csv"
SCREENING_CACHE_META = DATA_DIR / "screening_meta.json"

DEFAULT_SAMPLE = {
    "SP500_SAMPLE": ["AAPL", "MSFT", "NVDA", "JNJ", "PG", "KO", "XOM", "HD", "V", "UNH"],
    "EURO_SAMPLE": ["ASML.AS", "SAP.DE", "TTE.PA", "SAN.MC", "ENI.MI", "UCG.MI"],
}

# ── Sanitizzazione ticker indici ───────────────────────────
SUFFIX_CODES = {"MI", "PA", "DE", "MC", "AS", "L", "SW", "ST", "BR"}
TICKER_RE = re.compile(r"^[A-Z0-9]{1,6}([.-][A-Z0-9]{1,4})?$")
TICKER_FIX = {
    "AIR.PA.DE": "AIR.DE",
    "MT.AS.PA": "MT.AS",
    "BT.A.L": "BT-A.L",
}

def _sanitize_ticker(t: str) -> str | None:
    t = (t or "").strip().upper()
    if not t or t == "NAN":
        return None
    if t in TICKER_FIX:
        return TICKER_FIX[t]
    parts = t.split(".")
    if len(parts) == 3 and parts[2] in SUFFIX_CODES:
        if parts[1] in SUFFIX_CODES:
            t = f"{parts[0]}.{parts[2]}"
        else:
            t = f"{parts[0]}-{parts[1]}.{parts[2]}"
    return t if TICKER_RE.match(t) else None

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
    """
    Storico lungo settimanale ancorato al Punto Zero post-recessione del 2009.
    Consente il calcolo dei drawdown reali dall'ATH senza tagliare la memoria storica.
    """
    df = yf.Ticker(ticker).history(start="2009-01-01", interval="1wk", auto_adjust=True)
    if df.empty:
        raise ValueError(f"Nessun dato lungo per {ticker}")
    df.index = pd.to_datetime(df.index)
    df = df[["High", "Low", "Close", "Volume"]]
    df = df.dropna(subset=["Close"])
    if df.empty:
        raise ValueError(f"Nessun dato lungo valido per {ticker}")
    return df

@st.cache_data(ttl=3600, show_spinner=False)
def download_ohlcv_chunked(tickers: tuple, period: str = "2y", chunk_size: int = 100) -> pd.DataFrame:
    tk = list(tickers)
    frames = []
    for i in range(0, len(tk), chunk_size):
        block = tk[i:i + chunk_size]
        try:
            raw = yf.download(block, period=period, interval="1d", auto_adjust=True, progress=False, threads=True)
        except Exception:
            continue
        if raw is None or raw.empty:
            continue
        if not isinstance(raw.columns, pd.MultiIndex):
            t0 = block[0]
            raw = pd.DataFrame({k: raw[k] for k in ["Open", "High", "Low", "Close", "Volume"]})
            raw.columns = pd.MultiIndex.from_product([raw.columns, [t0]])
        frames.append(raw[["Open", "High", "Low", "Close", "Volume"]])
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
            raw = yf.download(block, start="2009-01-01", interval="1wk", auto_adjust=True, progress=False, threads=True)
        except Exception:
            continue
        if raw is None or raw.empty:
            continue
        if not isinstance(raw.columns, pd.MultiIndex):
            t0 = block[0]
            raw = pd.DataFrame({("Close", t0): raw["Close"], ("Volume", t0): raw["Volume"], ("High", t0): raw["High"], ("Low", t0): raw["Low"]})
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
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - prev).abs(), (df["Low"] - prev).abs()], axis=1).max(axis=1)
    val = float(tr.rolling(period).mean().iloc[-1])
    return 0.0 if np.isnan(val) else val

def vwap_anchored(df: pd.DataFrame, lookback: int = 60) -> float:
    w = df.tail(lookback)
    typical = (w["High"] + w["Low"] + w["Close"]) / 3
    vol = w["Volume"].replace(0, np.nan)
    val = float((typical * vol).sum() / vol.sum())
    return float(w["Close"].iloc[-1]) if np.isnan(val) else val

# ── Zone volumetriche multiple (HLC & Recency Preventiva - TIGHT SENSITIVITY) ─────────────────────
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

def volume_zones(wdf: pd.DataFrame, bins: int = 150, max_zones: int = 5, half_life_years: float = 4.0, min_share: float = 0.02, max_width_frac: float = 0.06, atr20: float | None = None, atr_width_mult: float = 3.5) -> list[dict]:
    """
    Calcola il Volume Profile con distribuzione HLC (40% Close, 30% High, 30% Low)
    e applica il decadimento temporale (recency) PREVENTIVO direttamente sui volumi storici.
    Sintonizzato con parametri 'Tight' per isolare mensole volumetriche strette e precise.
    """
    if wdf is None or len(wdf) < 40:
        return []
    
    high = wdf["High"].to_numpy()
    low = wdf["Low"].to_numpy()
    close = wdf["Close"].to_numpy()
    vol = wdf["Volume"].fillna(0).to_numpy()
    
    total_vol = float(vol.sum())
    if total_vol <= 0:
        return []
        
    age_base = ((wdf.index[-1] - wdf.index).days / 365.25).to_numpy()
    
    # Distribuzione HLC: 40% Close, 30% High, 30% Low
    prices_flat = np.concatenate([close, high, low])
    volumes_flat = np.concatenate([vol * 0.40, vol * 0.30, vol * 0.30])
    age_flat = np.concatenate([age_base, age_base, age_base])
    
    # Calcolo della recency esponenziale
    recency_flat = np.exp(-age_flat / half_life_years)
    
    pmin, pmax = float(prices_flat.min()), float(prices_flat.max())
    if pmax <= pmin:
        return []
        
    price_bins = np.linspace(pmin, pmax, bins + 1)
    bin_w = (pmax - pmin) / bins
    
    idx = np.clip(np.searchsorted(price_bins, prices_flat, side="right") - 1, 0, bins - 1)
    
    # Pesatura preventiva: sgonfiamo i vecchi volumi prima del bincount
    vp_weighted = np.bincount(idx, weights=volumes_flat * recency_flat, minlength=bins).astype(float)
    vp_raw = np.bincount(idx, weights=volumes_flat, minlength=bins).astype(float)
    
    # Convoluzione per smussare le asperità del profilo pesato
    vps = np.convolve(vp_weighted, np.array([0.25, 0.5, 0.25]), mode="same")
    
    pos = vps[vps > 0]
    if pos.size == 0:
        return []
    thr = float(np.percentile(pos, 82))  # Percentile rigido all'82% per sintonizzazione Tight
    
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
                zv = float(vp_raw[l:h + 1].sum())
                share = zv / total_vol
                if share < min_share:
                    continue
                z_weight_sum = float(vp_weighted[l:h + 1].sum())
                zones.append({
                    "lo": float(price_bins[l]),
                    "hi": float(price_bins[h + 1]),
                    "center": float((price_bins[l] + price_bins[h + 1]) / 2),
                    "share": share,
                    "weighted_sum": z_weight_sum,
                    "age": float(age_base[-1])
                })
            i = j + 1
        else:
            i += 1
            
    if not zones:
        return []
        
    mx_weight = max(z["weighted_sum"] for z in zones)
    for z in zones:
        z["score"] = int(round(100 * (z["weighted_sum"] / mx_weight))) if mx_weight > 0 else 0
        z["recency"] = 1.0  # già incorporata
        
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

def structural_anchors(wdf: pd.DataFrame, k: int = 13, min_gap_weeks: int = 26, max_n: int = 3, earnings: list | None = None) -> list[dict]:
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
    # CORREZIONE ERRORE: ordinamento basato solo sull'elemento 0 per evitare il TypeError delle tuple
    cand.sort(key=lambda x: -x[0])
    chosen = []
    for sel, i, near in cand:
        if all(abs(i - c["i"]) >= min_gap_weeks for c in chosen):
            chosen.append({"i": i, "date": wdf.index[i], "price": float(low.iloc[i]), "near": near, "rise": float(rise.iloc[i])})
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

def confluence_score(z1: dict | None, z2: dict | None, vwaps: list, atr20: float | None, price: float | None) -> int:
    """
    Punteggio 0-100 di confluenza volumetrica multi-timeframe: premia i casi in
    cui la zona secondaria (Z2) e/o gli VWAP ancorati (VWA1-VWA3) cadono vicini
    al centro della zona primaria (Z1, il POC Maestro pesato sul profilo lungo
    periodo). Decadimento esponenziale sulla distanza, non soglia binaria: un
    livello a metà tolleranza pesa meno di uno perfettamente coincidente ma non
    viene azzerato.
    Tolleranza ATR-based per coerenza con zone_component/atr_width_mult già
    usati altrove nel modulo (2x ATR20, minimo 0.5% del prezzo).
    Pesi (sommano a 1.0): Z2 0.30, VWA1 0.35, VWA2 0.20, VWA3 0.15 — i VWAP
    ancorati pesano di più perché sono un riferimento strutturale indipendente
    dal profilo volumetrico, non un suo sotto-prodotto.
    """
    if not z1 or not atr20 or atr20 <= 0:
        return 0
    ref = z1["center"]
    tol = max(atr20 * 2.0, (price or ref) * 0.005)
    if tol <= 0:
        return 0
    candidates = [
        (z2["center"] if z2 else None, 0.30),
        (vwaps[0] if len(vwaps) > 0 else None, 0.35),
        (vwaps[1] if len(vwaps) > 1 else None, 0.20),
        (vwaps[2] if len(vwaps) > 2 else None, 0.15),
    ]
    total = 0.0
    for val, w in candidates:
        if val is None:
            continue
        dist = abs(val - ref)
        total += w * np.exp(-dist / tol)
    return int(round(100 * min(1.0, total)))

TOTAL_BONUS_CAP = 18  # tetto sulla SOMMA bonus_sector + bonus_confluence in Priorità
# (sotto la somma dei due massimi individuali, 15+10=25: forza una compressione
# quando entrambi i bonus sono alti insieme, invece di sommarsi senza limite)

def bonus_confluence(score: int | None, max_bonus: int = 10) -> int:
    """
    Bonus di Priorità da 0 a `max_bonus`, SOLO positivo: un livello con alta
    confluenza è più solido, ma bassa confluenza non è "contro" — a differenza
    del settore (che può essere a favore o contro trend), Confluenza misura
    forza strutturale, non direzione. Cap separato dal bonus di settore (±15)
    perché questa metrica non è ancora validata da backtest: la teniamo
    volutamente più piccola finché non abbiamo dati reali dalle Simulazioni.
    """
    if not score:
        return 0
    return int(round(np.clip(score, 0, 100) / 100 * max_bonus))

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
        return {"score": 0, "drawdown": 0.0, "rsi": 50.0, "roc10": 0.0, "decel": 0.0, "components": {"drawdown": 0.0, "rsi": 50.0, "zone": 50.0, "decel": 50.0}}
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
    total = (0.4 * components["drawdown"] + 0.2 * components["rsi"] + 0.2 * components["zone"] + 0.2 * components["decel"])
    return {"score": int(round(float(np.nan_to_num(total)))), "drawdown": drawdown, "rsi": r, "roc10": roc_now, "decel": decel, "components": components}

# ── RILEVATORE SIFREDIANA (Hidden Market Model) ───────────────
def check_sifrediana(df: pd.DataFrame, i: int, period: int = 20) -> tuple[bool, dict]:
    """
    Rileva se la candela all'indice 'i' è una vera candela Sifrediana secondo
    l'Hidden Market Model: variazione simultanea e prepotente di:
    - MOMENTUM (Chiusura fortissima, vicino ai massimi del range)
    - VOLUME (Soldi reali istituzionali)
    - VOLATILITÀ (Range che distrugge la volatilità media precedente)
    """
    if i < period:
        return False, {}
        
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]
    
    range_candela = high.iloc[i] - low.iloc[i]
    if range_candela <= 0:
        return False, {}
    close_pos = (close.iloc[i] - low.iloc[i]) / range_candela
    momentum_ok = close_pos >= 0.85
    
    vol_sma = volume.iloc[max(0, i-period):i].mean()
    volume_ratio = volume.iloc[i] / vol_sma if vol_sma > 0 else 0.0
    volume_ok = volume_ratio >= 1.5
    
    prev_df = df.iloc[max(0, i-period):i]
    tr_list = []
    for k in range(1, len(prev_df)):
        tr = max(
            prev_df["High"].iloc[k] - prev_df["Low"].iloc[k],
            abs(prev_df["High"].iloc[k] - prev_df["Close"].iloc[k-1]),
            abs(prev_df["Low"].iloc[k] - prev_df["Close"].iloc[k-1])
        )
        tr_list.append(tr)
    avg_tr = np.mean(tr_list) if tr_list else range_candela
    volatility_ratio = range_candela / avg_tr if avg_tr > 0 else 1.0
    volatility_ok = volatility_ratio >= 1.5
    
    is_sif = bool(momentum_ok and volume_ok and volatility_ok and close.iloc[i] > close.iloc[i-1])
    
    details = {
        "is_sifrediana": is_sif,
        "close_position": round(close_pos, 2),
        "volume_ratio": round(volume_ratio, 2),
        "volatility_ratio": round(volatility_ratio, 2),
        "close_price": round(close.iloc[i], 2)
    }
    return is_sif, details

# ── REVERSAL STATE ────────────────────────────────────────
def _cross_recent(above: np.ndarray, lookback: int = 5) -> bool:
    n = len(above)
    if n < 2:
        return False
    return any(bool(above[-i]) and not bool(above[-i - 1]) for i in range(1, min(lookback, n - 1) + 1))

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

def reversal_state(df: pd.DataFrame, wdf: pd.DataFrame, zones: list[dict], anchors: list[dict], hc_score: int, es_positive: bool | None = None) -> dict:
    close = df["Close"]
    if len(close) < 30:
        return {"dd": 0.0, "points": 0, "kind": None, "flags": {"B": False, "C": False, "G": False, "D": False, "E": False}, "sifrediana_today": False, "sif_details": {}}
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
    
    # Rilevazione della Sifrediana negli ultimi 3 giorni per convalidare il breakout (D)
    any_sif = False
    for offset in range(min(3, len(close))):
        is_sif, _ = check_sifrediana(df, len(close) - 1 - offset)
        if is_sif:
            any_sif = True
            break
            
    # Se c'è una Sifrediana recente, convalidiamo d'ufficio la spinta D
    if any_sif:
        D = True
        
    qual = bool(hc_score >= 40) and (es_positive is not False)
    d1p, d2p = _d12(df, len(close) - 2)
    persist = bool(d3 or ((d1 or d2) and (d1p or d2p or d3)))
    E = bool(qual and persist)
    points = int(B) + int(C) + 2 * int(G) + int(D) + int(E)
    
    kind = None
    # Sifrediana SPECIFICAMENTE sulla candela corrente di oggi (ultimo elemento)
    today_sif, today_sif_details = check_sifrediana(df, len(close) - 1)
    
    if today_sif:
        kind = "🟢"  # Sblocca l'avviso immediato bypassando completamente il drawdown e i punti
    elif dd <= -20:
        # Con Sifrediana recente, diamo la sufficienza per il segnale verde 🟢 a 4/6 punti (anziché 5/6)
        if (points >= 5 and D) or (points >= 4 and any_sif):
            kind = "🟢"
        elif points >= 2:
            kind = "🟡"
            
    return {
        "dd": dd, 
        "points": points, 
        "kind": kind, 
        "flags": {"B": B, "C": C, "G": G, "D": D, "E": E},
        "sifrediana_today": today_sif,
        "sif_details": today_sif_details if today_sif else {}
    }

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

def earnings_badge(ticker: str, warn_days: int = 3) -> str:
    """Badge da mostrare in tabella se la trimestrale è entro `warn_days` giorni.
    Riusa earnings_dates_list (già in cache 24h), nessuna chiamata di rete
    aggiuntiva. Ritorna '—' se nessuna trimestrale imminente o dato assente."""
    dates = earnings_dates_list(ticker)
    if not dates:
        return "—"
    today = pd.Timestamp.now().date()
    future = [d.date() for d in dates if d.date() >= today]
    if not future:
        return "—"
    days_to = (min(future) - today).days
    if days_to == 0:
        return "⚠️ Trimestrale oggi"
    if days_to <= warn_days:
        return f"⚠️ Trimestrale <{days_to}gg"
    return "—"

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
            out = []
            for x in df[col].dropna():
                t = _sanitize_ticker(str(x))
                if t and t not in out:
                    out.append(t)
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
            wdf = pd.DataFrame({"High": hw, "Low": lw, "Close": cw, "Volume": vw.reindex(cw.index)}).dropna()
            if len(wdf) >= 40:
                return wdf
        except Exception:
            pass
    return sub

def screening(tickers: list[str], log=None, progress_cb=None) -> tuple[pd.DataFrame, dict]:
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
    _log("Download OHLCV daily a blocchi (cache 1h)…")
    try:
        data = download_ohlcv_chunked(tuple(tickers))
    except Exception:
        _log("Download daily fallito.")
        return pd.DataFrame(), {"total": total, "valid": 0, "discarded": total}
    _log("Download settimanale lungo a blocchi (cache 6h)…")
    try:
        data_w = download_weekly_chunked(tuple(tickers))
    except Exception:
        data_w = None
    _log("Settimanale non disponibile: zone su daily 2y.")
    _log("Elaborazione: zone, VWAP ancorati, reversal state, health, Wyckoff…")
    try:
        sec_rows, sec_src = sector_rows()
    except Exception:
        sec_rows, sec_src = {}, "n/d"
    try:
        sub_rows_map, sub_src = sub_rows()
    except Exception:
        sub_rows_map, sub_src = {}, "n/d"
    _log(f"Sector rotation: {len(sec_rows)} settori GICS + {len(sub_rows_map)} sotto-settori ({sec_src}).")
    rows = []
    for i, t in enumerate(tickers):
        if i and i % 100 == 0:
            _log(f"… elaborati {i}/{total}")
        if progress_cb is not None:
            try:
                progress_cb(i + 1, total)
            except Exception:
                pass
        try:
            c = data["Close"][t].dropna()
            v = data["Volume"][t].dropna()
            o = data["Open"][t].reindex(c.index)
            h = data["High"][t].reindex(c.index)
            l = data["Low"][t].reindex(c.index)
            if len(c) < 80:
                continue
            sub = pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": v})
            sub = sub.dropna(subset=["Close"])
            price = float(c.iloc[-1])
            vwap60 = vwap_anchored(sub)
            a20 = atr(sub)
            wdf = _weekly_for(data_w, t, sub)
            zones = volume_zones(wdf, atr20=a20)
            anchors = structural_anchors(wdf)
            bs = bottom_score(sub, zones=zones)
            hc = health_check(t)
            rev = reversal_state(sub, wdf, zones, anchors, hc["score"])
            # Risolto: zones[0]["center"] invece di zones["center"]
            wyk = wyckoff_analysis(sub, poc_price=zones[0]["center"] if zones else None)
            z1 = zones[0] if zones else None
            z2 = zones[1] if len(zones) > 1 else None
            in_lbl = ""
            for zi, z in enumerate(zones, 1):
                if z["lo"] <= price <= z["hi"]:
                    in_lbl = f"Z{zi}"
                    break
            # Risolto: anchors[0]["vwap"] invece di anchors["vwap"]
            vwa1 = anchors[0]["vwap"] if anchors else None
            vwa2 = anchors[1]["vwap"] if len(anchors) > 1 else None
            vwa3 = anchors[2]["vwap"] if len(anchors) > 2 else None
            conf_val = confluence_score(z1, z2, [vwa1, vwa2, vwa3], a20, price)
            wyk_str = f"{wyk['score_10']}/10" if wyk["n_events"] >= 2 else "—"
            sec_key = sub_key = sec_score = sec_breadth = sec_prio = None
            sub_lbl = sub_score = sub_delta = None
            sec_label, sec_etf, sec_vento = "—", "—", "nd"
            try:
                sec_key, sub_key = sector_of(t), sub_of(t)
                _srow = (sec_rows or {}).get(sec_key or "")
                sec_score = _srow["score"] if _srow else None
                sec_breadth = (_srow or {}).get("spread")
                sec_vento = vento(sec_key, sec_rows)
                if sec_key:
                    sec_label = sector_label(sec_key)
                    if rev["kind"] and sec_vento == "contro":
                        sec_label = f"⚠️ {sec_label}"
                if _srow:
                    sec_etf = " · ".join(x for x in (_srow.get("cw"), _srow.get("ew")) if x)
                _sub = (sub_rows_map or {}).get(sub_key or "")
                if _sub:
                    sub_lbl = _sub["label"]
                    sub_score = _sub.get("score")
                    sub_delta = _sub.get("d63")
                if bs["score"] is not None:
                    # Cap complessivo TOTAL_BONUS_CAP sulla SOMMA dei due bonus,
                    # non sui singoli: preso da solo ognuno arriva rispettivamente
                    # a ±15 (settore) e 0..+10 (confluenza), ma sommati senza un
                    # tetto comune un titolo con entrambi alti salirebbe in
                    # Priorità più di uno con Bottom Score migliore ma senza
                    # bonus — un'interazione che nessuno dei due limiti singoli,
                    # pensati in isolamento, teneva conto.
                    combined_bonus = int(np.clip(
                        bonus_sector(sec_score) + bonus_confluence(conf_val),
                        -TOTAL_BONUS_CAP, TOTAL_BONUS_CAP))
                    sec_prio = int(round(bs["score"] + combined_bonus))
            except Exception:
                pass
            rows.append({
                "Ticker": t,
                "Nome": company_name(t),
                "Prezzo": round(price, 2),
                "DD%": round(bs["drawdown"], 1),
                "RSI": round(bs["rsi"], 0),
                "VWAP60": round(vwap60, 2),
                "VWA1": round(vwa1, 2) if vwa1 else None,
                "VWA2": round(vwa2, 2) if vwa2 else None,
                "VWA3": round(vwa3, 2) if vwa3 else None,
                "Z1": f"{z1['lo']:.2f}–{z1['hi']:.2f} ·{z1['score']}" if z1 else "—",
                "Z2": f"{z2['lo']:.2f}–{z2['hi']:.2f} ·{z2['score']}" if z2 else "—",
                "Z1c": round(z1["center"], 4) if z1 else None,
                "In zona": in_lbl,
                "Segnale": f"{rev['kind']} {rev['points']}/6" if rev["kind"] else "—",
                "Sifrediana_Today": rev.get("sifrediana_today", False),
                "Sif_Details": rev.get("sif_details", {}),
                "Health": hc["score"],
                "Bottom": bs["score"],
                "Wyckoff": wyk_str,
                "W_Score": wyk["score_10"] if wyk["n_events"] >= 2 else 0,
                "Settore": sec_label,
                "SettoreKey": sec_key or "",
                "Sector": sector_cell(sec_key, sec_rows),
                "SectorETF": sec_etf,
                "SectorScore": round(sec_score) if sec_score is not None else None,
                "Δ EW−CW": round(sec_breadth, 1) if sec_breadth is not None else None,
                "Vento": sec_vento,
                "Sotto-settore": sub_lbl or "—",
                "SottoKey": sub_key or "",
                "SottoScore": round(sub_score) if sub_score is not None else None,
                "SottoΔ": round(sub_delta, 1) if sub_delta is not None else None,
                "Priorità": sec_prio,
                "Avviso": earnings_badge(t),
                "Confluenza": conf_val,
            })
        except Exception:
            continue
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("Bottom", ascending=False).reset_index(drop=True)
    diagnostics = {"total": total, "valid": len(rows), "discarded": total - len(rows)}
    diagnostics["sector_classified"] = sum(1 for r in rows if r.get("SettoreKey"))
    diagnostics["sub_classified"] = sum(1 for r in rows if r.get("SottoKey"))
    diagnostics["sector_source"] = sec_src
    diagnostics["sub_source"] = sub_src
    _log(f"Completato: {len(rows)} validi, {total - len(rows)} scartati.")
    return out, diagnostics

# ── Universo & risoluzione ticker ──────────────────────────
SUFFIXES = ["", ".MI", ".PA", ".DE", ".MC", ".AS", ".L", ".SW", ".ST", ".BR"]
@st.cache_data(ttl=3600, show_spinner=False)
def build_universe() -> list[str]:
    from core.sectors import etf_universe
    tickers = set()
    for name in DEFAULT_SAMPLE:
        tickers.update(DEFAULT_SAMPLE[name])
    try:
        tickers.update(etf_universe())
    except Exception:
        pass
    if INDICES_DIR.exists():
        for p in INDICES_DIR.glob("*.csv"):
            try:
                df = pd.read_csv(p)
                col = "Ticker" if "Ticker" in df.columns else df.columns[0]
                for x in df[col].dropna():
                    t = _sanitize_ticker(str(x))
                    if t:
                        tickers.add(t)
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

# ── Mappatura TradingView ─────────────────────────────────
TV_EXCHANGES = {
    "": "NASDAQ",
    ".MI": "MIL",
    ".PA": "EURONEXT",
    ".DE": "XETR",
    ".MC": "BMAD",
    ".AS": "EURONEXT",
    ".L": "LSE",
    ".SW": "SIX",
    ".ST": "OMX",
    ".BR": "EURONEXT",
}

def tradingview_url(ticker: str) -> str:
    if "." in ticker:
        base, suffix = ticker.rsplit(".", 1)
        suffix = "." + suffix.upper()
    else:
        base, suffix = ticker, ""
    ex = TV_EXCHANGES.get(suffix, "NASDAQ")
    return f"https://www.tradingview.com/chart/?symbol={ex}:{base}"
