"""
Checker alert standalone (GitHub Actions o locale).
Carica la watchlist per REVERSAL/LIVELLI e lo screening globale per i CANDELONI.
Invia Telegram e registra lo stato SOLO a invio riuscito.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from core.reversal import analyze_ticker
from core.watchlist_io import load_watchlist
from core.data_engine import (
    bottom_score,
    company_name,
    tradingview_url,
    load_screening_cache,
)
from core.sectors import snapshot_and_source, sector_label, vento as vento_sector
from core.regime import compute_regime
from core.alerts import (
    check_alerts,
    check_regime_change,
    register_regime_notified,
    send_telegram,
    _register_sent_alert,
    _aggiungi_trade_simulazione,
)


def _build_state(e: dict, a: dict, srows: dict) -> dict:
    df = a["df"]
    close = df["Close"]
    price = float(close.iloc[-1])
    prev_close = float(close.iloc[-2]) if len(close) > 1 else None
    bs = bottom_score(df, zones=a["zones"])
    wyk = a["wyckoff"]
    rev = a["rev"]
    sec_key = a.get("sector")
    sec_row = (srows or {}).get(sec_key) if sec_key else None
    return {
        "nome": company_name(e["ticker"]),
        "price": price,
        "prev_close": prev_close,
        "dd": bs["drawdown"],
        "rsi": bs["rsi"],
        "segnale": f"{rev['kind']} {rev['points']}/6" if rev["kind"] else "—",
        "wyckoff": f"{wyk['score_10']}/10" if wyk["n_events"] >= 2 else "—",
        "sifrediana_today": bool(rev.get("sifrediana_today", False)),
        "sector_score": (sec_row or {}).get("score"),
        "vento": vento_sector(sec_key, srows) if sec_key else "nd",
        "settore": sector_label(sec_key) if sec_key else "—",
        "sotto": a.get("sub") or "—",
        "bottom": bs["score"],
        "link_tv": tradingview_url(e["ticker"]),
    }


def main() -> None:
    # 1. Carica Watchlist per REVERSAL e LIVELLI
    entries = load_watchlist()
    snap, _src = snapshot_and_source()
    srows = {
        k: v
        for k, v in (snap or {}).get("rows", {}).items()
        if v.get("livello") == "settore"
    }

    states = {}
    if entries:
        for e in entries:
            a = analyze_ticker(e["ticker"])
            if a is None:
                continue
            states[e["ticker"]] = _build_state(e, a, srows)

    # 2. Carica Screening Globale (per i CANDELONI fuori watchlist)
    df_screening_global = None
    try:
        df_screening_global, _ = load_screening_cache()
    except Exception as e:
        print(f"⚠️ Impossibile caricare cache screening globale: {e}")

    # 3. Ottieni candidati (check_alerts NON salva il JSON)
    alerts_to_send = check_alerts(entries, states, df_screening_global)

    # 3b. Cambio Regime (dedup a stato, separato dal day_lock a 5gg)
    regime_candidate = check_regime_change(compute_regime())
    if regime_candidate:
        alerts_to_send.append(regime_candidate)

    if not alerts_to_send:
        print("Nessun nuovo alert.")
        return

    # 4. Invio e Registrazione (il timer 5gg parte solo qui)
    success_count = 0
    for a in alerts_to_send:
        sent = send_telegram(a["text"])
        if sent:
            if a["type"] == "REGIME_CHANGE":
                register_regime_notified(a["regime"])
            else:
                _register_sent_alert(
                    a["ticker"], a["type"], price=a.get("price"), score=a.get("score")
                )
                _aggiungi_trade_simulazione(a)
            etichetta = a["text"].splitlines()[0][:80]
            print(f"[{a['type']}] {etichetta} → Telegram: ok")
            success_count += 1
        else:
            etichetta = a["text"].splitlines()[0][:80]
            print(
                f"[{a['type']}] {etichetta} → Telegram: FALLITO "
                f"(non registrato, ritenterà al prossimo ciclo)"
            )

    print(
        f"Processo completato: {success_count}/{len(alerts_to_send)} "
        f"alert inviati con successo."
    )


if __name__ == "__main__":
    main()
