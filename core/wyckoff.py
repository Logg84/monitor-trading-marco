"""
Wyckoff accumulation pattern detection on daily OHLCV data.
Rileva la sequenza SC → AR → ST → Spring → SOS → LPS
e produce un punteggio 0-100 + mapping 1-10 per la screening.
Bonus cross-conferma con POC dalle zone volumetriche.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def _sma(s: pd.Series, w: int) -> pd.Series:
    return s.rolling(w).mean()


def _close_position(df: pd.DataFrame, i: int) -> float:
    hi = float(df["High"].iloc[i])
    lo = float(df["Low"].iloc[i])
    if hi <= lo:
        return 0.5
    return (float(df["Close"].iloc[i]) - lo) / (hi - lo)


def _atr_at(df: pd.DataFrame, i: int, period: int = 20) -> float:
    sub = df.iloc[max(0, i - period + 1):i + 1]
    if len(sub) < period:
        return 0.0
    prev = sub["Close"].shift(1)
    tr = pd.concat([
        sub["High"] - sub["Low"],
        (sub["High"] - prev).abs(),
        (sub["Low"] - prev).abs(),
    ], axis=1).max(axis=1)
    val = float(tr.mean())
    return 0.0 if np.isnan(val) else val


def wyckoff_analysis(df: pd.DataFrame, poc_price: float | None = None) -> dict:
    """
    Rilevamento pattern Wyckoff su OHLCV giornaliero.
    Restituisce score 0-100, mappato a 1-10, eventi e confidenza.
    """
    if df is None or len(df) < 120:
        return {"score": 0, "score_10": 1, "confidence": "bassa",
                "events": [], "n_events": 0}

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    vol = df["Volume"].fillna(0)
    price = float(close.iloc[-1])
    hi_all = float(high.max())
    dd = (price / hi_all - 1) * 100

    if dd > -15:
        return {"score": 0, "score_10": 1, "confidence": "bassa",
                "events": [], "n_events": 0}

    vol_sma20 = _sma(vol, 20)
    atr20 = _atr_at(df, len(df) - 1)

    n = len(df)
    events = []
    event_details = {}

    # ── 1. SELLING CLIMAX ──────────────────────────────────
    sc_candidates = []
    lookback = min(n - 30, 180)
    start = n - lookback
    for i in range(start, n - 5):
        if vol_sma20.iloc[i] <= 0:
            continue
        vol_ratio = float(vol.iloc[i]) / float(vol_sma20.iloc[i])
        if vol_ratio < 2.0:
            continue
        ret = float(close.iloc[i]) / float(close.iloc[max(0, i - 5)]) - 1
        if ret > -0.02:
            continue
        cp = _close_position(df, i)
        if cp > 0.35:
            continue
        a20 = _atr_at(df, i)
        if a20 <= 0:
            continue
        sc_candidates.append({
            "i": i, "date": df.index[i],
            "low": float(low.iloc[i]), "close": float(close.iloc[i]),
            "vol_ratio": vol_ratio, "cp": cp, "atr": a20,
        })

    if not sc_candidates:
        return {"score": 0, "score_10": 1, "confidence": "bassa",
                "events": [], "n_events": 0}

    sc = min(sc_candidates, key=lambda x: x["close"])
    i_sc = sc["i"]
    sc_low = sc["low"]
    sc_price = sc["close"]
    events.append("SC")
    event_details["SC"] = {
        "date": str(sc["date"].date()),
        "price": sc_price, "vol_ratio": round(sc["vol_ratio"], 1),
        "atr": round(sc["atr"], 2),
    }
    sc_vol = float(vol.iloc[i_sc])

    # ── 2. AUTOMATIC RALLY ─────────────────────────────────
    ar_high = sc_price
    ar_idx = i_sc
    for i in range(i_sc + 2, min(i_sc + 15, n)):
        if float(close.iloc[i]) > ar_high:
            ar_high = float(close.iloc[i])
            ar_idx = i
    max_since_sc = float(high.iloc[i_sc:ar_idx + 1].max())
    ar_threshold = ar_high if ar_high > sc_price * 1.03 else max_since_sc
    if ar_threshold > sc_price * 0.97:
        events.append("AR")
        event_details["AR"] = {
            "date": str(df.index[ar_idx].date()),
            "high": round(ar_threshold, 2),
            "days": ar_idx - i_sc,
        }

    # ── 3. SECONDARY TEST ──────────────────────────────────
    st_found = False
    for i in range(ar_idx + 2, n - 3):
        if float(low.iloc[i]) <= sc_low * 1.05 and float(low.iloc[i]) >= sc_low * 0.95:
            vol_ratio_st = float(vol.iloc[i]) / sc_vol if sc_vol > 0 else 0
            if vol_ratio_st < 0.7:
                cp_st = _close_position(df, i)
                if cp_st > 0.4:
                    st_found = True
                    events.append("ST")
                    event_details["ST"] = {
                        "date": str(df.index[i].date()),
                        "low": round(float(low.iloc[i]), 2),
                        "vol_ratio_to_sc": round(vol_ratio_st, 2),
                        "close_pos": round(cp_st, 2),
                    }
                    break

    # ── 4. SPRING ──────────────────────────────────────────
    spring_found = False
    spring_quality = 0.0
    for i in range(start, n - 3):
        if float(close.iloc[i]) < sc_low * 0.99:
            for j in range(i + 1, min(i + 6, n)):
                if float(close.iloc[j]) > sc_low * 0.995:
                    spring_vol_down = float(vol.iloc[i]) / float(vol_sma20.iloc[i]) if vol_sma20.iloc[i] > 0 else 1
                    spring_vol_up = float(vol.iloc[j]) / float(vol_sma20.iloc[j]) if vol_sma20.iloc[j] > 0 else 1
                    spring_quality = min(1.0, spring_vol_up / max(0.1, spring_vol_down))
                    spring_found = True
                    events.append("Spring")
                    event_details["Spring"] = {
                        "break_date": str(df.index[i].date()),
                        "return_date": str(df.index[j].date()),
                        "break_price": round(float(close.iloc[i]), 2),
                        "return_price": round(float(close.iloc[j]), 2),
                        "quality": round(spring_quality, 2),
                    }
                    break
            if spring_found:
                break

    # ── 5. SIGN OF STRENGTH ────────────────────────────────
    sos_found = False
    for i in range(ar_idx + 2, n):
        if float(close.iloc[i]) > ar_threshold * 1.01:
            if vol_sma20.iloc[i] > 0 and float(vol.iloc[i]) / float(vol_sma20.iloc[i]) > 1.3:
                sos_found = True
                events.append("SOS")
                event_details["SOS"] = {
                    "date": str(df.index[i].date()),
                    "price": round(float(close.iloc[i]), 2),
                    "vol_ratio": round(float(vol.iloc[i]) / float(vol_sma20.iloc[i]), 1),
                }
                break

    # ── 6. LAST POINT OF SUPPORT ───────────────────────────
    lps_found = False
    if sos_found:
        sos_idx_candidate = None
        for i in range(n - 15, n - 1):
            if float(close.iloc[i]) > ar_threshold:
                sos_idx_candidate = i
        if sos_idx_candidate is not None and sos_idx_candidate < n - 3:
            for i in range(sos_idx_candidate + 1, n):
                retrace = float(close.iloc[i]) / float(close.iloc[sos_idx_candidate]) - 1
                if -0.05 < retrace < 0:
                    lps_vol = float(vol.iloc[i]) / float(vol_sma20.iloc[i]) if vol_sma20.iloc[i] > 0 else 1
                    if lps_vol < 1.2:
                        lps_found = True
                        events.append("LPS")
                        event_details["LPS"] = {
                            "date": str(df.index[i].date()),
                            "price": round(float(close.iloc[i]), 2),
                            "retrace": round(retrace * 100, 1),
                            "vol_ratio": round(lps_vol, 1),
                        }
                        break

    n_events = len(events)

    # ── SCORE CALCULATION ──────────────────────────────────
    score = 0
    if "SC" in events:
        score += 15
    if "AR" in events:
        score += 8
    if "ST" in events:
        st_vol_quality = event_details.get("ST", {}).get("vol_ratio_to_sc", 0.5)
        st_bonus = max(0, min(20, int((0.7 - st_vol_quality) * 50)))
        score += 10 + st_bonus
    if "Spring" in events:
        sq = event_details.get("Spring", {}).get("quality", 0.5)
        score += 10 + min(15, int(sq * 15))
    if "SOS" in events:
        score += 12
    if "LPS" in events:
        score += 10

    # POC cross-confirmation bonus
    poc_bonus = 0
    if poc_price is not None and poc_price > 0:
        for ev_name in ("Spring", "LPS"):
            ev = event_details.get(ev_name, {})
            if ev:
                ev_price = ev.get("return_price") or ev.get("price") or 0
                if ev_price > 0 and abs(ev_price - poc_price) / max(poc_price, 0.01) < 0.03:
                    poc_bonus = 10
                    break

    score = min(100, score + poc_bonus)
    score_10 = max(1, min(10, round(score / 10))) if n_events >= 2 else max(1, min(10, round(score / 15)))

    # ── CONFIDENCE ─────────────────────────────────────────
    confidence = "alta"
    missing_days = sum(1 for i in range(1, 200) if not pd.isna(close.iloc[i]))
    avg_vol = float(vol.tail(60).mean()) if len(vol) > 60 else 0
    if avg_vol < 200_000:
        confidence = "bassa"
    elif n < 200 or atr20 / max(price, 0.01) < 0.005:
        confidence = "media"
    if missing_days < 180:
        confidence = "bassa"

    return {
        "score": score,
        "score_10": score_10,
        "confidence": confidence,
        "events": events,
        "n_events": n_events,
        "details": event_details,
        "poc_bonus": poc_bonus > 0,
        "sc_price": sc_price,
        "sc_low": sc_low,
    }