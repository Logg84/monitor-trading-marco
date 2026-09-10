"""
Screening schedulato: unione indici → screening → cache → auto-popolazione
watchlist 🤖 → pruning (🤖 e 👤). I risultati vengono committati dal workflow.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.data_engine import (
    INDICES_DIR, load_index_constituents, screening, save_screening_cache,
)
from core.reversal import auto_populate, prune_watchlist

def main() -> None:
    names = sorted(p.stem for p in INDICES_DIR.glob("*.csv")) if INDICES_DIR.exists() else []
    if not names:
        print("Nessun indice disponibile.")
        return
    per_index = {}
    raw = []
    for n in names:
        tks = load_index_constituents(n)
        per_index[n] = len(tks)
        raw.extend(tks)
    tickers = sorted(set(raw))
    print(f"Unione: {len(raw)} lordi → {len(tickers)} unici")

    # Snapshot di settore (ETF cap-weighted + equal-weighted): viene scritto in
    # data/sectors_latest.json e committato dal workflow: è il fallback del
    # portale quando il live download non riesce, e la sua età va dichiarata.
    try:
        from core.sectors import sector_snapshot
        snap = sector_snapshot()
        print("Settori: " + ("ok" if snap else "NESSUN dato (n/d)")
              + f" · {len((snap or {}).get('rows', {}))} settori")
    except Exception as e:
        print(f"Settori: non disponibili ({e})")

    df, diag = screening(tickers, log=print)
    if df.empty:
        print("Screening senza risultati.")
        return
    save_screening_cache(df, {"index": "📊 VISUALIZZA TUTTI INSIEME",
                              "diagnostics": diag, "per_index": per_index,
                              "gross": len(raw)})

    added = auto_populate(df.to_dict("records"))
    print(f"Auto-popolazione: {len(added)} aggiunti → {added[:10]}")

    removed = prune_watchlist()
    for t, motivo in removed:
        print(f"Pruning: rimosso {t} ({motivo})")

if __name__ == "__main__":
    main()
