"""
Watchlist: schema, I/O, riconciliazione, livelli manuali L1/L2/L3.
👤 manuale = intoccabile dall'automazione; 🤖 auto = gestita dal sistema.
REGOLA D'ORO: reconcile NON rimuove mai le entry (aggiorna solo i campi).
Le uscite 🤖 avvengono SOLO via core.reversal.prune_watchlist
(condizione vera per 5 chiusure consecutive). Niente killer silenziosi.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
WATCHLIST_PATH = DATA_DIR / "watchlist.json"

STALE_MONTHS = 4

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

def load_watchlist_with_restore() -> list[dict]:
    """
    Come load_watchlist, ma se il file locale è vuoto prova a ripristinare
    da data/watchlist.json nel repo GitHub (fonte di verità).
    Serve a guarire il portale dopo un redeploy o un publish anomalo.
    """
    entries = load_watchlist()
    if entries:
        return entries
    try:
        from core.gh_sync import fetch_json_from_github
        data = fetch_json_from_github("data/watchlist.json")
        if data and data.get("entries"):
            save_watchlist(data["entries"])
            return data["entries"]
    except Exception:
        pass
    return entries

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
    """
    Aggiorna i campi derivati (vwap, poc auto) e basta.
    NON rimuove mai: le uscite sono competenza di prune_watchlist.
    Cintura: se per qualsiasi ragione l'output fosse vuoto con input pieno,
    blocca il salvataggio e segnala.
    """
    out, msgs = [], []
    for e in entries:
        m = metrics.get(e["ticker"])
        if m is None:
            out.append(e)
            continue
        e["vwap"] = m.get("vwap")
        if e["origin"] == "auto":
            e["poc"] = m.get("poc_auto")
            e["poc_origin"] = "auto"
        out.append(e)
    if entries and not out:
        msgs.append("🛡 reconcile: svuotamento rilevato e bloccato (protezione).")
        return entries, msgs
    save_watchlist(out)
    return out, msgs
