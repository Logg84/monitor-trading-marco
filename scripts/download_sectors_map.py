"""
Costruisce data/sector_map.json: ticker → {key, sector, industry} per tutti i
costituenti degli indici (e i benchmark di settore). Serve da terzo livello di
classificazione quando Yahoo non espone settore/industria (tipico di alcune
mid cap europee e ADR): senza questo file il titolo resta "—" (n/d), mai forzato.

Uso:  python scripts/download_sectors_map.py [--refresh]
Il file va committato a mano (pattern identico a data/indices/*.csv): NON viene
mai scritto dal portale, che lo legge e basta.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.data_engine import INDICES_DIR, load_index_constituents, get_info
from core.sectors import SECTORS, classify, etf_universe

OUT = Path(__file__).resolve().parent.parent / "data" / "sector_map.json"


def main(refresh: bool) -> None:
    names = sorted(p.stem for p in INDICES_DIR.glob("*.csv")) if INDICES_DIR.exists() else []
    tickers = sorted({t for n in names for t in load_index_constituents(n)} | set(etf_universe()))
    if not tickers:
        print("Nessun ticker: genera i CSV indici (scripts/download_indices.py --force).")
        return
    old = {}
    if OUT.exists() and not refresh:
        try:
            old = json.loads(OUT.read_text()).get("map", {})
        except Exception:
            old = {}
    out, n_cls = dict(old), 0
    for i, t in enumerate(tickers, 1):
        if t in old and not refresh:
            continue
        info = get_info(t) or {}
        sect, ind = info.get("sector"), info.get("industry")
        gics, sotto, tema = classify(sect, ind)
        out[t] = {"key": gics or "", "sub": sotto or "", "tema": tema or "",
                  "sector": sect or "", "industry": ind or ""}
        n_cls += bool(gics)
        if i % 100 == 0:
            print(f"… {i}/{len(tickers)}")
    OUT.write_text(json.dumps(
        {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "chiavi": {k: v["label"] for k, v in SECTORS.items()},
         "map": out}, ensure_ascii=False, sort_keys=True))
    tot = len(out)
    print(f"sector_map.json: {tot} ticker, {n_cls} con settore GICS ora "
          f"({100 * n_cls / max(tot, 1):.0f}% di copertura sul nuovo giro)")
    print("Committa il file (dati di lettura, non di stato come la watchlist).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="ignora la mappa esistente")
    main(ap.parse_args().refresh)
