"""
Checker alert standalone (GitHub Actions o locale).
Costruisce gli stati reversal per la watchlist e invia Telegram.
Tipi: CANDIDATO / INVERSIONE / LIVELLO_L1..L3.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.reversal import analyze_ticker
from core.watchlist_io import load_watchlist
from core.alerts import check_alerts, send_telegram

def main() -> None:
    entries = load_watchlist()
    if not entries:
        print("Watchlist vuota: nessun alert possibile.")
        return
    states = {}
    for e in entries:
        a = analyze_ticker(e["ticker"])
        if a is None:
            continue
        close = a["df"]["Close"]
        states[e["ticker"]] = {
            "price": float(close.iloc[-1]),
            "prev_close": float(close.iloc[-2]) if len(close) > 1 else None,
            "kind": a["rev"]["kind"],
            "points": a["rev"]["points"],
        }
    alerts = check_alerts(entries, states)
    if not alerts:
        print("Nessun nuovo alert.")
        return
    for a in alerts:
        sent = send_telegram(a["text"])
        print(f"{a['text']} → Telegram: {'ok' if sent else 'non configurato'}")

if __name__ == "__main__":
    main()
