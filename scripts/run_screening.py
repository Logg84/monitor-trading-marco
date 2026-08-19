"""
Screening schedulato: unione indici → screening → cache → auto-popolazione
watchlist 🤖 → pruning (🤖 e ). I risultati vengono committati dal workflow.
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
