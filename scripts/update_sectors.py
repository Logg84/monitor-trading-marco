"""
Aggiornamento serale dei settori (dopo la chiusura di Wall Street): riscrive
data/sectors_latest.json, che è il fallback del portale e la fonte dello stato
di settore usato dagli alert. Leggero: ~50 ETF in una batch, nessun download di
storici lunghi, nessuna analisi sui singoli titoli.

Uso:
  python scripts/update_sectors.py            # scrive la cache, non notifica
  SETTORI_NOTIFICA=1 python scripts/update_sectors.py   # + digest Telegram

Il flag di notifica è deliberatamente spento nel cron: un messaggio al giorno va
deciso, non ereditato. I numeri sono CHIUSURE: se il job corre a mercato ainda
aperto, la barra del giorno è parziale e il campo `market_open_bar` lo dichiara.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.sectors import digest_should_notify, rotation_digest, sector_snapshot
from core.alerts import send_telegram


def main() -> int:
    snap = sector_snapshot()
    if not snap:
        print("Nessun dato di settore: download ETF fallito (yfinance transitorio?) "
              "e cache del repo assente o di formato vecchio. La cache NON viene "
              "sovrascritta con un file vuoto.")
        return 1
    rows = snap.get("rows", {})
    n_live = sum(1 for r in rows.values() if r.get("score") is not None)
    print(f"settori aggiornati: snapshot {snap['saved_at']} · chiusura "
          f"{snap.get('asof')} · {n_live}/{len(rows)} unita con stato "
          f"(fonte prezzi: chiusure giornaliere, {'barra di oggi parziale' if snap.get('market_open_bar') else 'chiusura consolidata'})")
    for r in sorted((r for r in rows.values() if r.get("livello") == "settore"),
                    key=lambda r: -(r.get("score") or 0)):
        d = r.get("d63")
        print(f"  {r['label']:26s} {r['emoji']} {r['score']:.0f}  3m {r['mom63']:+5.1f}%"
              f"  Δ {'n/d' if d is None else f'{d:+.1f}'}")
    if digest_should_notify():
        testo = rotation_digest(snap)
        if testo:
            ok = send_telegram(testo)
            print("digest Telegram:", "inviato" if ok else
                  "NON inviato (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID non configurati)")
    else:
        print("digest Telegram: disattivato (SETTORI_NOTIFICA non impostato)")
    print("cache scritta in data/sectors_latest.json (la committa il workflow)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
