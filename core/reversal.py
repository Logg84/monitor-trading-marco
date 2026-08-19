"""
Operazioni watchlist basate sul reversal state:
- analyze_ticker: pacchetto completo per un ticker
- auto_populate: promuove 🟡/🟢 dello screening in watchlist 🤖 (write-through GitHub)
- prune_watchlist: uscite automatiche (🤖 e ) con persistenza 5 chiusure (write-through).
Regole uscita (punti come da reversal_state, 🟡 a ≥2):
 🤖: (DD > −20% OR punti < 2) per 5 chiusure consecutive.
 👤: (punti < 2 AND chiusura < livello minimo inserito) per 5 chiusure consecutive.
 👤 senza livelli inseriti: nessuna uscita automatica.
"""
from __future__ import annotations
import streamlit as st
from core.data_engine import (
    get_prices, get_prices_long, atr, volume_zones, structural_anchors,
    earnings_dates_list, earnings_snapshot, health_check, reversal_state,
    candidate_at,
)
from core.watchlist_io import load_watchlist, add_entry, remove_entry
from core.gh_sync import publish_watchlist

@st.cache_data(ttl=3600, show_spinner=False)
def analyze_ticker(ticker: str) -> dict | None:
    try:
        df = get_prices(ticker)
    except Exception:
        return None
    a20 = atr(df)
    try:
        wdf = get_prices_long(ticker)
    except Exception:
        wdf = df
    zones = volume_zones(wdf, atr20=a20)
    anchors = structural_anchors(wdf, earnings=earnings_dates_list(ticker))
    hc = health_check(ticker)
    es = earnings_snapshot(ticker)
    rev = reversal_state(df, wdf, zones, anchors, hc["score"], es["positive"])
    return {"df": df, "wdf": wdf, "zones": zones, "anchors": anchors,
            "hc": hc, "es": es, "rev": rev}

def auto_populate(rows) -> list[str]:
    """Aggiunge in watchlist (🤖) i ticker 🟡/🟢 assenti. Ritorna i ticker aggiunti."""
    entries = load_watchlist()
    have = {e["ticker"] for e in entries}
    added = []
    for r in rows:
        sig = str(r.get("Segnale", ""))
        t = r["Ticker"]
        if sig.startswith(("🟡", "🟢")) and t not in have:
            try:
                add_entry(t, origin="auto", poc=r.get("Z1c"))
                added.append(t)
                have.add(t)
            except Exception:
                continue
    if added:
        try:
            publish_watchlist()
        except Exception:
            pass
    return added

def _bad_series(a: dict, origin: str, min_lvl: float | None) -> bool:
    """True se la condizione di uscita vale sulle ultime 5 chiusure."""
    df = a["df"]
    n = len(df["Close"])
    if n < 30:
        return False
    D = a["rev"]["flags"]["D"]
    E = a["rev"]["flags"]["E"]
    idxs = range(max(25, n - 5), n)
    for i in idxs:
        dd_i, pts_i = candidate_at(df, a["zones"], a["anchors"], i, D, E)
        if origin == "auto":
            if not ((dd_i > -20) or (pts_i < 2)):
                return False
        else:
            close_i = float(df["Close"].iloc[i])
            if not (pts_i < 2 and min_lvl is not None and close_i < min_lvl):
                return False
    return True

def prune_watchlist() -> list[tuple[str, str]]:
    """Rimuove entry che soddisfano le condizioni di uscita. Ritorna [(ticker, motivo)]."""
    entries = load_watchlist()
    removed = []
    for e in entries:
        a = analyze_ticker(e["ticker"])
        if a is None:
            continue
        min_lvl = None
        if e["origin"] == "manual":
            lv = [v for v in (e.get("levels") or {}).values() if v]
            if not lv:
                continue
            min_lvl = min(lv)
        if _bad_series(a, e["origin"], min_lvl):
            motivo = ("sconto recuperato o sotto soglia candidato"
                      if e["origin"] == "auto"
                      else "non candidato e sotto il livello minimo inserito")
            try:
                remove_entry(e["ticker"])
                removed.append((e["ticker"], motivo))
            except Exception:
                continue
    if removed:
        try:
            publish_watchlist()
        except Exception:
            pass
    return removed
