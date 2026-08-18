"""
Bussola: 6 attori di mercato → composite → regime LONG/NEUTRO/SHORT.
Attori senza dati (COT non caricato) pesano 0 e vengono rinormalizzati.
Lettura contrarian per operatore medio-lungo: paura estrema = opportunità,
euforia = rischio.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

@st.cache_data(ttl=3600, show_spinner=False)
def _close(ticker: str, period: str = "3y") -> pd.Series:
    try:
        df = yf.Ticker(ticker).history(period=period, auto_adjust=True)
    except Exception:
        return pd.Series(dtype=float)
    return df["Close"].dropna() if not df.empty else pd.Series(dtype=float)

def _clip(x: float) -> float:
    return float(np.clip(x, -100, 100))

def _nodata(name: str, detail: str) -> dict:
    return {"name": name, "score": 0.0, "source": "no data", "detail": detail}

def actor_institutions() -> dict:
    s = _close("^GSPC")
    if len(s) < 210:
        return _nodata("Istituzionali", "SPX non disponibile")
    price = float(s.iloc[-1])
    sma = float(s.rolling(200).mean().iloc[-1])
    mom = float(s.pct_change(63).iloc[-1] * 100)
    score = (50 if price > sma else -50) + float(np.clip(mom * 5, -50, 50))
    return {"name": "Istituzionali", "score": _clip(score), "source": "SPX vs SMA200",
            "detail": f"prezzo {'sopra' if price > sma else 'sotto'} SMA200; mom 3M {mom:+.1f}%"}

def actor_risk_managers() -> dict:
    v = _close("^VIX")
    if v.empty:
        return _nodata("Risk manager", "VIX non disponibile")
    level = float(v.iloc[-1])
    slope = float(v.iloc[-1] - v.iloc[-21]) if len(v) > 21 else 0.0
    level_score = float(np.clip((level - 20) * 5, -60, 60))  # paura = opportunità
    slope_score = float(np.clip(-slope * 4, -40, 40))        # VIX calante = panico che rientra
    return {"name": "Risk manager", "score": _clip(level_score + slope_score),
            "source": "VIX", "detail": f"VIX {level:.1f}; pendenza 1M {slope:+.1f}"}

def actor_vol_vol() -> dict:
    vv = _close("^VVIX")
    v = _close("^VIX")
    if vv.empty or v.empty or float(v.iloc[-1]) <= 0:
        return _nodata("Vol of vol", "VVIX/VIX non disponibile")
    ratio = float(vv.iloc[-1]) / float(v.iloc[-1])
    score = float(np.clip((ratio - 1.0) * 150, -100, 100))
    return {"name": "Vol of vol", "score": _clip(score), "source": "VVIX/VIX",
            "detail": f"ratio {ratio:.2f} (>1.2 stress, <0.9 compiacenza)"}

def actor_retail() -> dict:
    p = _close("^PCP")
    if p.empty:
        return _nodata("Retail (contrarian)", "put/call non disponibile")
    pc = float(p.iloc[-1])
    score = float(np.clip((pc - 0.9) * 200, -100, 100))
    return {"name": "Retail (contrarian)", "score": _clip(score), "source": "put/call CBOE",
            "detail": f"put/call {pc:.2f} (>1 paura, <0.7 euforia)"}

def actor_managed_money(cot: dict | None) -> dict:
    if not cot or "managed_money" not in cot:
        return {"name": "Money manager", "score": 0.0, "source": "COT assente",
                "detail": "carica il report dalla pagina COT"}
    return {"name": "Money manager", "score": _clip(cot["managed_money"]),
            "source": "COT", "detail": cot.get("managed_money_detail", "")}

def actor_producers(cot: dict | None) -> dict:
    if not cot or "producers" not in cot:
        return {"name": "Produttori", "score": 0.0, "source": "COT assente",
                "detail": "carica il report dalla pagina COT"}
    return {"name": "Produttori", "score": _clip(cot["producers"]),
            "source": "COT", "detail": cot.get("producers_detail", "")}

WEIGHTS = {
    "Istituzionali": 0.25, "Risk manager": 0.20, "Vol of vol": 0.15,
    "Retail (contrarian)": 0.15, "Money manager": 0.15, "Produttori": 0.10,
}

def compute_regime(cot: dict | None = None) -> dict:
    actors = [
        actor_institutions(), actor_risk_managers(), actor_vol_vol(),
        actor_retail(), actor_managed_money(cot), actor_producers(cot),
    ]
    usable = [a for a in actors if a["source"] not in ("no data", "COT assente")]
    den = sum(WEIGHTS[a["name"]] for a in usable)
    composite = (sum(a["score"] * WEIGHTS[a["name"]] for a in usable) / den) if den else 0.0
    regime = "LONG" if composite > 15 else ("SHORT" if composite < -15 else "NEUTRO")
    return {"actors": actors, "composite": float(composite), "regime": regime}