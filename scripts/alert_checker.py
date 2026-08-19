"""
Checker alert standalone (GitHub Actions o locale).
Calcola metriche watchlist, genera alert, invia Telegram se configurato.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.data_engine import get_prices, atr, vwap_anchored, poc_zone, rsi
from core.watchlist_io import load_watchlist
from core.alerts import check_alerts, send_telegram

def metrics_for(ticker: str, poc_manual: float | None) -> dict | None:
    try:
        df = get_prices(ticker)
    except Exception:
        return None
    price = float(df["Close"].iloc[-1])
    vwap = vwap_anchored(df)
    poc = poc_manual or vwap
    lo, hi = poc_zone(poc, atr(df))
    return {"price": price, "vwap": vwap, "poc_lo": lo, "poc_hi": hi,
            "rsi": float(rsi(df["Close"]).iloc[-1])}

def main() -> None:
    entries = load_watchlist()
    if not entries:
        print("Watchlist vuota: nessun alert possibile.")
        return

    metrics = {}
    for e in entries:
        m = metrics_for(e["ticker"], e.get("poc") if e.get("poc_origin") == "manual" else None)
        if m:
            metrics[e["ticker"]] = m

    alerts = check_alerts(entries, metrics)
    if not alerts:
        print("Nessun nuovo alert.")
        return

    for a in alerts:
        emoji = "🟡" if a["kind"] == "VWAP_TOUCH" else "🟢"
        text = (f"{emoji} {a['ticker']} — {a['kind']} @ {a['price']:.2f} "
                f"(RSI {a['rsi']:.0f})")
        sent = send_telegram(text)
        print(f"{text} → Telegram: {'ok' if sent else 'non configurato'}")

if __name__ == "__main__":
    main()