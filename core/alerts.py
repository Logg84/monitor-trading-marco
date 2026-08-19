"""
Alert: tocco VWAP ±2% e prezzo dentro zona POC.
Cooldown dinamico (Proposta 2), niente duplicati a mercati chiusi,
Telegram opzionale se il token esiste.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ALERTS_PATH = DATA_DIR / "alerts.json"

def _now() -> datetime:
    return datetime.now(timezone.utc)

def load_alert_state() -> dict:
    if ALERTS_PATH.exists():
        try:
            with open(ALERTS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"history": [], "last_sent": {}, "last_price": {}}

def save_alert_state(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(ALERTS_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def cooldown_days(rsi: float, price: float, vwap: float | None) -> int:
    """Proposta 2: 1g se RSI>70 e prezzo sopra VWAP (trend forte),
    altrimenti 3g (laterale)."""
    if vwap and rsi > 70 and price > vwap:
        return 1
    return 3

def check_alerts(entries: list[dict], metrics: dict[str, dict]) -> list[dict]:
    """metrics: {ticker: {price, vwap, poc_lo, poc_hi, rsi}}"""
    state = load_alert_state()
    new_alerts = []

    for e in entries:
        t = e["ticker"]
        m = metrics.get(t)
        if not m:
            continue
        price = m["price"]

        # Prezzo invariato → mercati chiusi → skip (niente duplicati)
        if state["last_price"].get(t) == price:
            continue
        state["last_price"][t] = price

        kinds = []
        vwap = m.get("vwap")
        if vwap and abs(price - vwap) / vwap <= 0.02:
            kinds.append("VWAP_TOUCH")
        lo, hi = m.get("poc_lo"), m.get("poc_hi")
        if lo is not None and hi is not None and lo <= price <= hi:
            kinds.append("POC_ZONE")

        for k in kinds:
            key = f"{t}:{k}"
            cd = cooldown_days(m.get("rsi", 50.0), price, vwap)
            last = state["last_sent"].get(key)
            if last:
                try:
                    if (_now() - datetime.fromisoformat(last)).days < cd:
                        continue
                except Exception:
                    pass
            alert = {"ticker": t, "kind": k, "price": price,
                     "rsi": m.get("rsi"), "ts": _now().isoformat()}
            new_alerts.append(alert)
            state["last_sent"][key] = _now().isoformat()
            state["history"].append(alert)

    state["history"] = state["history"][-200:]
    save_alert_state(state)
    return new_alerts

def send_telegram(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": text}, timeout=10)
        return bool(r.ok)
    except Exception:
        return False