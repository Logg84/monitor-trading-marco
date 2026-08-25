"""
Alert: CANDIDATO / INVERSIONE / LIVELLO (L1-L3).
Regole rumore:
- max 1 alert/giorno/titolo;
- stessa tipologia sullo stesso titolo: non prima di 5 giorni;
- prezzo invariato → mercati chiusi → skip.
Telegram opzionale se i token esistono.
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import requests

from core.data_engine import company_name

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ALERTS_PATH = DATA_DIR / "alerts.json"

# ── Mercato di riferimento dal suffisso ticker ──────────────
MARKET_NAMES = {
    "": "USA (S&P/Nasdaq)",
    ".MI": "FTSE MIB (Italia)",
    ".PA": "CAC 40 (Francia)",
    ".DE": "DAX (Germania)",
    ".MC": "IBEX 35 (Spagna)",
    ".AS": "AEX (Paesi Bassi)",
    ".L": "FTSE 100 (UK)",
    ".SW": "SMI (Svizzera)",
    ".ST": "OMX (Svezia)",
    ".BR": "BEL 20 (Belgio)",
}

def _market_name(ticker: str) -> str:
    if "." in ticker:
        suffix = "." + ticker.rsplit(".", 1)[-1].upper()
    else:
        suffix = ""
    return MARKET_NAMES.get(suffix, "—")

def _label(ticker: str) -> str:
    """'TICKER (Nome Azienda · Mercato)' pronto per i messaggi alert."""
    try:
        name = company_name(ticker)
    except Exception:
        name = "—"
    return f"{ticker} ({name} · {_market_name(ticker)})"

def _now() -> datetime:
    return datetime.now(timezone.utc)

def load_alert_state() -> dict:
    if ALERTS_PATH.exists():
        try:
            with open(ALERTS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"history": [], "last_sent": {}, "last_price": {}, "day_lock": {},
            "target_fired": {}}

def save_alert_state(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(ALERTS_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def check_alerts(entries: list[dict], states: dict) -> list[dict]:
    """states: {ticker: {price, prev_close, kind (None/🟡/), points}}"""
    st_ = load_alert_state()
    st_.setdefault("day_lock", {})
    st_.setdefault("target_fired", {})
    today = _now().date().isoformat()
    out = []
    for e in entries:
        t = e["ticker"]
        s = states.get(t)
        if not s:
            continue
        price = s["price"]
        if st_["last_price"].get(t) == price:
            continue
        st_["last_price"][t] = price
        if st_["day_lock"].get(t) == today:
            continue

        kinds = []
        prev = s.get("prev_close")
        lbl = _label(t)
        for lvl, val in (e.get("levels") or {}).items():
            if val and prev is not None and ((prev < val <= price) or (prev > val >= price)):
                kinds.append((f"LIVELLO_{lvl}",
                              f"📏 {lbl} chiude {price:.2f} e incrocia {lvl} @ {val:.2f}"))
        if s.get("kind") == "🟡":
            kinds.append(("CANDIDATO",
                          f"🟡 {lbl} CANDIDATO ({s['points']}/6) @ {price:.2f}"))
        if s.get("kind") == "🟢":
            kinds.append(("INVERSIONE",
                          f"🟢 {lbl} INVERSIONE IN ATTO ({s['points']}/6) @ {price:.2f}"))

        # ── TARGET_DATE ─────────────────────────────────────
        td = e.get("target_date")
        if td and not st_["target_fired"].get(t):
            try:
                if today >= td:
                    kinds.append(("TARGET_DATE",
                                  f"📅 {lbl} — DATA TARGET RAGGIUNTA ({td}) @ {price:.2f}"))
                    st_["target_fired"][t] = True
            except Exception:
                pass

        fired = False
        for kind, text in kinds:
            key = f"{t}:{kind}"
            last = st_["last_sent"].get(key)
            if last:
                try:
                    if (_now() - datetime.fromisoformat(last)).days < 5:
                        continue
                except Exception:
                    pass
            alert = {"ticker": t, "kind": kind, "price": price,
                     "ts": _now().isoformat(), "text": text}
            out.append(alert)
            st_["last_sent"][key] = _now().isoformat()
            st_["history"].append(alert)
            fired = True
        if fired:
            st_["day_lock"][t] = today
    st_["history"] = st_["history"][-200:]
    save_alert_state(st_)
    return out

def send_telegram(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": text,
                                "parse_mode": "Markdown"}, timeout=10)
        return bool(r.ok)
    except Exception:
        return False
