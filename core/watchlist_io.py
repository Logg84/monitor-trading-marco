"""
Watchlist: schema, I/O, riconciliazione, livelli manuali L1/L2/L3.
👤 manuale = intoccabile dall'automazione; 🤖 auto = gestita dal sistema.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
WATCHLIST_PATH = DATA_DIR / "watchlist.json"

STALE_MONTHS = 4
ZOMBIE_DD_PCT = -8.0

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def load_watchlist() -> list[dict]:
    if not WATCHLIST_PATH.exists():
        return []
    try:
        with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("entries", [])
    except Exception:
        return []

def save_watchlist(entries: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(WATCHLIST_PATH, "w", encoding="utf-8") as f:
        json.dump({"updated": _now(), "entries": entries},
                  f, indent=2, ensure_ascii=False)

def add_entry(ticker: str, origin: str = "manual",
              poc: float | None = None, notes: str = "") -> list[dict]:
    entries = load_watchlist()
    if any(e["ticker"] == ticker for e in entries):
        return entries
    poc_origin = None
    if poc is not None:
        poc_origin = "manual" if origin == "manual" else "auto"
    entries.append({
        "ticker": ticker,
        "origin": origin,
        "created": _now(),
        "last_reviewed": _now(),
        "poc": poc,
        "poc_origin": poc_origin,
        "vwap": None,
        "levels": {},  # L1, L2, L3 manuali
        "notes": notes,
    })
    save_watchlist(entries)
    return entries

def remove_entry(ticker: str) -> list[dict]:
    entries = [e for e in load_watchlist() if e["ticker"] != ticker]
    save_watchlist(entries)
    return entries

def touch_review(ticker: str) -> list[dict]:
    entries = load_watchlist()
    for e in entries:
        if e["ticker"] == ticker:
            e["last_reviewed"] = _now()
    save_watchlist(entries)
    return entries

def update_levels(ticker: str, levels: dict) -> list[dict]:
    entries = load_watchlist()
    for e in entries:
        if e["ticker"] == ticker:
            e["levels"] = levels
    save_watchlist(entries)
    return entries

def is_stale(entry: dict) -> bool:
    if entry.get("origin") != "manual":
        return False
    ref = entry.get("last_reviewed") or entry.get("created")
    if not ref:
        return True
    try:
        dt = datetime.fromisoformat(ref)
    except Exception:
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).days > STALE_MONTHS * 30

def reconcile(entries: list[dict],
              metrics: dict[str, dict]) -> tuple[list[dict], list[str]]:
    out, msgs = [], []
    for e in entries:
        m = metrics.get(e["ticker"])
        if m is None:
            out.append(e)
            continue
        e["vwap"] = m.get("vwap")
        if e["origin"] == "auto":
            dd = m.get("drawdown")
            if dd is not None and dd > ZOMBIE_DD_PCT:
                msgs.append(f"🤖 {e['ticker']} rimosso: sconto perso (DD {dd:.1f}%)")
                continue
            e["poc"] = m.get("poc_auto")
            e["poc_origin"] = "auto"
        out.append(e)
    save_watchlist(out)
    return out, msgs