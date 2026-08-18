"""
Screening daily multi-indice + riconciliazione watchlist.
Salva data/screening_latest.csv.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from core.data_engine import (
    DEFAULT_SAMPLE, INDICES_DIR, DATA_DIR, load_index_constituents,
    screening, get_prices, vwap_anchored,
)
from core.watchlist_io import load_watchlist, reconcile

def main() -> None:
    names = list(DEFAULT_SAMPLE.keys())
    if INDICES_DIR.exists():
        names += [p.stem for p in INDICES_DIR.glob("*.csv") if p.stem not in names]

    frames = []
    for name in names:
        tickers = load_index_constituents(name)
        if not tickers:
            continue
        try:
            df = screening(tickers)
        except Exception as e:
            print(f"Screening {name} fallito: {e}")
            continue
        if not df.empty:
            df["Index"] = name
            frames.append(df)
            print(f"{name}: {len(df)} titoli")

    if frames:
        out = pd.concat(frames, ignore_index=True)
        out = out.sort_values("Bottom", ascending=False)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        out.to_csv(DATA_DIR / "screening_latest.csv", index=False)
        print(f"Salvati {len(out)} righe in screening_latest.csv")

    # Riconcilia watchlist: VWAP sempre, POC solo 🤖, zombie rimossi
    entries = load_watchlist()
    metrics = {}
    for e in entries:
        try:
            df = get_prices(e["ticker"])
        except Exception:
            continue
        price = float(df["Close"].iloc[-1])
        ath = float(df["Close"].max())
        metrics[e["ticker"]] = {
            "vwap": round(vwap_anchored(df), 4),
            "poc_auto": round(vwap_anchored(df), 4),
            "drawdown": (price / ath - 1) * 100,
        }
    _, msgs = reconcile(entries, metrics)
    for m in msgs:
        print(m)

if __name__ == "__main__":
    main()