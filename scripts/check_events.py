"""
Checker eventi calendario standalone (GitHub Actions o locale).
Recupera eventi da tutte le fonti, confronta con lo stato salvato,
invia alert Telegram per eventi in scadenza (entro N giorni).
"""
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import event_calendar as EC
from core.alerts import send_telegram, load_alert_state, save_alert_state

DAYS_AHEAD = 14

def main() -> None:
    now = datetime.datetime.now(datetime.UTC)
    log_entry = {"ts": now.isoformat(), "event": "check_started"}

    try:
        # 1. Fetch nuovi eventi
        new_events = EC.fetch_all_events()
        if new_events:
            EC.save_events(new_events)
            print(f"[OK] Salvati {len(new_events)} eventi.")
            log_entry["event"] = f"salvati_{len(new_events)}_eventi"
        else:
            print("[WARN] Nessun evento recuperato.")
            log_entry["event"] = "nessun_evento"

        # 2. Controlla eventi in scadenza
        upcoming = EC.check_upcoming_events(days_ahead=DAYS_AHEAD)
        if not upcoming:
            print(f"[OK] Nessun evento in scadenza nei prossimi {DAYS_AHEAD} giorni.")
            log_entry["upcoming"] = 0
        else:
            print(f"[ALERT] {len(upcoming)} eventi in scadenza nei prossimi {DAYS_AHEAD} giorni:")
            for e in upcoming:
                text = EC.build_alert_text(e)
                print(f"\n{text}")
                sent = send_telegram(text)
                print(f"  → Telegram: {'✅' if sent else '❌ (non configurato)'}")
            log_entry["upcoming"] = len(upcoming)
            log_entry["event"] = f"alert_{len(upcoming)}_eventi"

    except Exception as e:
        print(f"[ERR] {e}")
        log_entry["event"] = f"errore: {e}"

    EC.save_check_log(log_entry)


if __name__ == "__main__":
    main()