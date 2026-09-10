"""
Bussola: 6 attori di mercato → composite → regime LONG/NEUTRO/SHORT.
Gli attori COT (Money manager, Produttori) si alimentano da
data/cot/cot_data.json se presente; altrimenti pesi rinormalizzati.

CORREZIONI APPLICATE (Settembre 2026):
- Retail (Put/Call): soglia equity P/C corretta a 0.7 (era 0.9)
- Pesi attori: bilanciati (Istituzionali 20%, Produttori 15%)
- VIX: soglie più conservative (20 come centro, non 20 come soglia)
- VVIX/VIX: centrato su 1.05 (media storica)
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

# ── PUT/CALL RATIO: Multi-source fallback ────────────────────
# CBOE ha smesso di pubblicare i feed gratuiti storici nel 2019.
# Usiamo 2 fonti in ordine di affidabilità:
# 1. SPY option chain (sempre disponibile via yfinance) - EQUITY P/C
# 2. VIX/VVIX ratio (proxy della paura retail)

@st.cache_data(ttl=3600, show_spinner=False)
def _putcall_ratio_spy() -> tuple[float | None, str]:
    """
    Put/Call ratio calcolato dal volume dell'option chain SPY.
    Questo è l'EQUITY P/C ratio specifico su SPY, non il Total P/C.
    Soglie corrette: <0.7 = euforia, >1.0 = paura estrema.
    """
    try:
        tk = yf.Ticker("SPY")
        exps = tk.options
        # Usa le prime 2 scadenze per avere più dati
        total_call_vol = 0.0
        total_put_vol = 0.0
        for exp in exps[:2]:
            chain = tk.option_chain(exp)
            total_call_vol += float(chain.calls["volume"].fillna(0).sum())
            total_put_vol += float(chain.puts["volume"].fillna(0).sum())
        
        if total_call_vol > 0:
            ratio = total_put_vol / total_call_vol
            return ratio, f"SPY opzioni (prime 2 scadenze)"
    except Exception as e:
        print(f"⚠️ Errore calcolo P/C da SPY: {e}")
    return None, ""

@st.cache_data(ttl=3600, show_spinner=False)
def _vix_skew_proxy() -> tuple[float | None, str]:
    """
    Proxy alternativo: VIX/VVIX ratio.
    Quando VIX è alto ma VVIX è basso = mercato spaventato ma stabile
    Quando VIX è basso ma VVIX è alto = compiacenza con paura futura
    Normalizziamo su scala simile al P/C ratio (0.5-1.5 range tipico).
    """
    try:
        vix = _close("^VIX", period="1mo")
        vvix = _close("^VVIX", period="1mo")
        if not vix.empty and not vvix.empty:
            # Ratio VVIX/VIX normalizzato
            ratio = float(vvix.iloc[-1]) / float(vix.iloc[-1])
            # Mappiamo su scala P/C-like: ratio tipico 0.8-1.2 → P/C 0.6-1.0
            # Se ratio > 1.2 = paura futura → P/C alto
            # Se ratio < 0.9 = compiacenza → P/C basso
            pc_proxy = 0.7 + (ratio - 1.0) * 0.8
            return pc_proxy, f"VIX/VVIX proxy (ratio {ratio:.2f})"
    except Exception:
        pass
    return None, ""

# ── ATTORI DI MERCATO ────────────────────────────────────────

def _clip(x: float) -> float:
    return float(np.clip(x, -100, 100))

def _nodata(name: str, detail: str) -> dict:
    return {"name": name, "score": 0.0, "source": "no data", "detail": detail}

def actor_institutions() -> dict:
    """Istituzionali: seguono il trend di lungo periodo (SMA200)."""
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
    """Risk manager: VIX alto = paura, slope negativa = miglioramento."""
    v = _close("^VIX")
    if v.empty:
        return _nodata("Risk manager", "VIX non disponibile")
    level = float(v.iloc[-1])
    slope = float(v.iloc[-1] - v.iloc[-21]) if len(v) > 21 else 0.0
    # CORREZIONE: soglie più conservative
    # VIX < 15 = bassa volatilità (score positivo)
    # VIX > 25 = alta volatilità (score negativo)
    level_score = float(np.clip((20 - level) * 4, -60, 60))
    slope_score = float(np.clip(-slope * 4, -40, 40))
    return {"name": "Risk manager", "score": _clip(level_score + slope_score),
            "source": "VIX", "detail": f"VIX {level:.1f}; pendenza 1M {slope:+.1f}"}

def actor_vol_vol() -> dict:
    """Vol of vol: VVIX/VIX ratio misura la paura della volatilità futura."""
    vv = _close("^VVIX")
    v = _close("^VIX")
    if vv.empty or v.empty or float(v.iloc[-1]) <= 0:
        return _nodata("Vol of vol", "VVIX/VIX non disponibile")
    ratio = float(vv.iloc[-1]) / float(v.iloc[-1])
    # CORREZIONE: soglia centrata su 1.05 (media storica)
    # ratio < 0.95 = compiacenza (score positivo)
    # ratio > 1.15 = stress (score negativo)
    score = float(np.clip((1.05 - ratio) * 200, -100, 100))
    return {"name": "Vol of vol", "score": _clip(score), "source": "VVIX/VIX",
            "detail": f"ratio {ratio:.2f} (>1.15 stress, <0.95 compiacenza)"}

def actor_retail() -> dict:
    """
    Retail (contrarian): Put/Call ratio.
    CORREZIONE: soglia equity P/C = 0.7 (non 0.9)
    <0.7 = euforia (score negativo, contrarian)
    >1.0 = paura estrema (score positivo, contrarian)
    """
    # Fonte 1: SPY option chain (equity P/C)
    pc, used_src = _putcall_ratio_spy()
    if pc is not None:
        # CORREZIONE: soglia 0.7 per equity P/C
        # pc < 0.7 = euforia → score negativo (contrarian: vendere)
        # pc > 1.0 = paura → score positivo (contrarian: comprare)
        if pc < 0.7:
            score = float(np.clip((0.7 - pc) * -300, -100, 0))
        elif pc > 1.0:
            score = float(np.clip((pc - 1.0) * 200, 0, 100))
        else:
            score = 0.0
        return {"name": "Retail (contrarian)", "score": _clip(score), "source": used_src,
                "detail": f"put/call {pc:.2f} (<0.7 euforia, >1.0 paura)"}
    
    # Fonte 2: VIX skew proxy (fallback)
    pc_proxy, proxy_src = _vix_skew_proxy()
    if pc_proxy is not None:
        score = float(np.clip((pc_proxy - 0.85) * 200, -100, 100))
        return {"name": "Retail (contrarian)", "score": _clip(score), "source": proxy_src,
                "detail": f"proxy {pc_proxy:.2f} (stima indiretta)"}
    
    return _nodata("Retail (contrarian)", "put/call non disponibile (nessuna fonte risolta)")

def _cot() -> dict | None:
    try:
        from core.cot import load_cot_data, regime_scores
        return regime_scores(load_cot_data())
    except Exception:
        return None

def actor_managed_money(cot: dict | None) -> dict:
    if not cot:
        return {"name": "Money manager", "score": 0.0, "source": "COT assente",
                "detail": "carica il report dalla pagina COT"}
    return {"name": "Money manager", "score": _clip(cot["managed_money"]),
            "source": "COT", "detail": cot.get("managed_money_detail", "")}

def actor_producers(cot: dict | None) -> dict:
    if not cot:
        return {"name": "Produttori", "score": 0.0, "source": "COT assente",
                "detail": "carica il report dalla pagina COT"}
    return {"name": "Produttori", "score": _clip(cot["producers"]),
            "source": "COT", "detail": cot.get("producers_detail", "")}

# ── PESI CORRETTI ────────────────────────────────────────────
# CORREZIONE: Bilanciamento migliore
# - Istituzionali: 20% (era 25%)
# - Risk manager: 20% (invariato)
# - Vol of vol: 10% (era 15%)
# - Retail: 15% (invariato)
# - Money manager: 20% (era 15%)
# - Produttori: 15% (era 10%) - aumentato perché hanno info privilegiata

WEIGHTS = {
    "Istituzionali": 0.20,
    "Risk manager": 0.20,
    "Vol of vol": 0.10,
    "Retail (contrarian)": 0.15,
    "Money manager": 0.20,
    "Produttori": 0.15,
}

@st.cache_data(ttl=900, show_spinner=False)
def _compute_regime_cached() -> dict:
    return _compute_regime_impl(_cot())

def compute_regime(cot: dict | None = None) -> dict:
    """Bussola: se non passi 'cot' esplicitamente il risultato è cachato
    15 minuti, così la navbar (che lo richiama ad ogni cambio pagina per
    il chip 🟢/🟡/🔴) non lo ricalcola da zero ogni volta."""
    if cot is not None:
        return _compute_regime_impl(cot)
    return _compute_regime_cached()

def _compute_regime_impl(cot: dict | None) -> dict:
    actors = [
        actor_institutions(), actor_risk_managers(), actor_vol_vol(),
        actor_retail(), actor_managed_money(cot), actor_producers(cot),
    ]
    usable = [a for a in actors if a["source"] not in ("no data", "COT assente")]
    den = sum(WEIGHTS[a["name"]] for a in usable)
    composite = (sum(a["score"] * WEIGHTS[a["name"]] for a in usable) / den) if den else 0.0
    regime = "LONG" if composite > 15 else ("SHORT" if composite < -15 else "NEUTRO")
    return {"actors": actors, "composite": float(composite), "regime": regime}
