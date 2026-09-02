"""
Operazioni watchlist basate sul reversal state:
- analyze_ticker: pacchetto completo per un ticker (incl. Wyckoff + chiavi
  settore/sotto-settore, che sono SOLO informative: le regole di ingresso e di
  uscita non le leggono)
- auto_populate: promuove 🟡/🟢 dello screening in watchlist 🤖 (write-through GitHub)
- prune_watchlist: uscite automatiche (🤖 e 👤) con persistenza 5 chiusure (write-through)
  e MESSAGGIO CON CAUSA REALE (quale ramo della regola è scattato).
CIRCUITO DI PROTEZIONE: il pruning non pubblica mai una watchlist che resterebbe
vuota (svuotamenti totali sono quasi sempre bug, non mercato).
Regole uscita (punti come da reversal_state, 🟡 a ≥2):
 🤖: (DD > −20% OR punti < 2) per 5 chiusure consecutive.
 👤: (punti < 2 AND chiusura < livello minimo inserito) per 5 chiusure consecutive.
 👤 senza livelli inseriti: nessuna uscita automatica.
 REGOLA: le entry con target_date non vengono mai rimosse.
"""
from __future__ import annotations
import numpy as np
import streamlit as st
from core.data_engine import (
    get_prices, get_prices_long, atr, volume_zones, structural_anchors,
    earnings_dates_list, earnings_snapshot, health_check, reversal_state,
)
from core.sectors import sector_of, sub_of
from core.wyckoff import wyckoff_analysis
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
    poc_price = zones[0]["center"] if zones else None
    wyk = wyckoff_analysis(df, poc_price=poc_price)
    # Chiave di settore: informativa (etichette, note, raggruppamenti). NON
    # entra in reversal_state né in _check_exit_conditions.
    try:
        sector, sub = sector_of(ticker), sub_of(ticker)
    except Exception:
        sector = sub = None
    return {"df": df, "wdf": wdf, "zones": zones, "anchors": anchors,
            "hc": hc, "es": es, "rev": rev, "wyckoff": wyk, "sector": sector, "sub": sub}

def auto_populate(rows) -> list[str]:
    """Aggiunge in watchlist (🤖) i ticker 🟡/🟢 assenti. Ritorna i ticker aggiunti."""
    entries = load_watchlist()
    have = {e["ticker"] for e in entries}
    added = []
    for r in rows:
        sig = str(r.get("Segnale", ""))
        t = r["Ticker"]
        # "" nella tupla rendeva questa condizione SEMPRE vera (ogni stringa
        # inizia con la stringa vuota in Python): venivano promosse anche
        # righe senza alcun segnale, poi rimosse quasi tutte dal pruning
        # subito successivo — tanto lavoro sprecato e watchlist finale
        # ridotta ai pochi sopravvissuti, non ai veri candidati 🟡/🟢.
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

def _check_exit_conditions(df, zones, anchors, D, E, origin, min_lvl,
                           points_threshold=2, dd_threshold=-20):
    """Verifica condizioni di uscita sulle ultime 5 chiusure.
    Versione ottimizzata: calcola RSI/ATR/medie una sola volta.
    Ritorna (bad, motivo): motivo descrive la CAUSA REALE dell'uscita
    (quale ramo della regola è scattato, con i valori odierni)."""
    close = df["Close"]
    n = len(close)
    if n < 30:
        return False, ""
    ma20 = close.rolling(20).mean()
    a20 = atr(df)
    idxs = list(range(max(25, n - 5), n))

    dd_days = pts_days = both_days = 0
    dd_last = pts_last = None
    price_last = None

    for i in idxs:
        c = close.iloc[:i + 1]
        price = float(c.iloc[-1])
        price_last = price
        dd = (price / float(c.max()) - 1) * 100
        roc = c.pct_change(10) * 100
        roc_now = float(roc.iloc[-1]) if not np.isnan(roc.iloc[-1]) else 0.0
        roc_prev = float(roc.iloc[-11]) if len(roc) > 11 and not np.isnan(roc.iloc[-11]) else roc_now
        decel = roc_now - roc_prev
        B = bool(decel > 0)
        in_zone, zscore = False, 0
        for z in zones:
            if z["lo"] <= price <= z["hi"]:
                in_zone = True
                zscore = max(zscore, z["score"])
        near_vwa = any(abs(price - an["vwap"]) <= a20 for an in anchors) if anchors else False
        C = bool((in_zone and zscore >= 50) or near_vwa)
        # Confronto per posizione (numpy), non per etichetta pandas:
        # 'c' è una porzione troncata di 'close' mentre 'ma20' copre l'intera
        # serie — confrontare i due Series direttamente fa scattare
        # "Can only compare identically-labeled Series objects" perché gli
        # indici non sono identici, anche se ma20 contiene semplicemente
        # più righe di c.
        above = (c.to_numpy() > ma20.iloc[:i + 1].to_numpy())
        cross = any(bool(above[-j]) and not bool(above[-j - 1])
                    for j in range(1, min(5, i) + 1)) if i >= 1 else False
        G = bool(above[-1] and cross)
        pts = int(B) + int(C) + 2 * int(G) + int(D) + int(E)
        dd_last, pts_last = dd, pts

        if origin == "auto":
            dd_bad = dd > dd_threshold
            pts_bad = pts < points_threshold
            if not (dd_bad or pts_bad):
                return False, ""
            if dd_bad and pts_bad:
                both_days += 1
            elif dd_bad:
                dd_days += 1
            else:
                pts_days += 1
        else:
            if not (pts < points_threshold and min_lvl is not None and price < min_lvl):
                return False, ""

    # ── Causa reale ─────────────────────────────────────────
    if origin == "manual":
        return True, (f"sotto soglia candidato ({pts_last}/6 < {points_threshold}) e chiusura "
                      f"{price_last:.2f} sotto il livello minimo inserito "
                      f"({min_lvl:.2f}) per 5 chiusure consecutive")
    if dd_days == 5:
        return True, (f"tornato sopra il ritracciamento minimo: drawdown "
                      f"{dd_last:+.1f}% (> {dd_threshold}%) per 5 chiusure consecutive")
    if pts_days == 5:
        return True, (f"sotto soglia candidato: {pts_last}/6 punti (< {points_threshold}) "
                      f"per 5 chiusure consecutive")
    return True, (f"causa mista su 5 chiusure: {dd_days + both_days}× tornato sopra il "
                  f"ritracciamento minimo, {pts_days + both_days}× sotto soglia candidato "
                  f"(DD oggi {dd_last:+.1f}%, punti oggi {pts_last}/6)")

def prune_watchlist(analyses: dict | None = None) -> list[tuple[str, str]]:
    """Rimuove entry che soddisfano le condizioni di uscita. Ritorna [(ticker, motivo_reale)].
    Se analyses è fornito (dict ticker→risultato analyze_ticker), li riusa
    invece di ricalcolare ogni entry.
    REGOLA: le entry con target_date non vengono mai rimosse."""
    entries = load_watchlist()
    removed = []
    for e in entries:
        if e.get("target_date"):
            continue
        a = analyses.get(e["ticker"]) if analyses else None
        if a is None:
            a2 = analyze_ticker(e["ticker"])
            if a2 is None:
                continue
            a = a2
        min_lvl = None
        if e["origin"] == "manual":
            lv = [v for v in (e.get("levels") or {}).values() if v]
            if not lv:
                continue
            min_lvl = min(lv)
        D = a["rev"]["flags"]["D"]
        E = a["rev"]["flags"]["E"]
        bad, motivo = _check_exit_conditions(a["df"], a["zones"], a["anchors"],
                                             D, E, e["origin"], min_lvl)
        if bad:
            try:
                remove_entry(e["ticker"])
                removed.append((e["ticker"], motivo))
            except Exception:
                continue
    if removed:
        remaining = len(load_watchlist())
        if remaining > 0:
            try:
                publish_watchlist()
            except Exception:
                pass
        else:
            st.warning(
                "Pruning avrebbe svuotato completamente la watchlist: "
                "pubblicazione su GitHub bloccata (circuito di protezione). "
                "Verifica core/watchlist_io.py e le regole di uscita.")
    return removed
