"""
core/macro_calendar.py

Banner globale (non per ticker) per eventi macro ad alta volatilità
imminenti: NFP, CPI, PCE, FOMC. Fonte: data/macro_events.json,
mantenuto a mano (nessuna API gratuita affidabile per queste date,
stesso motivo per cui in event_calendar.py lo scraping è sconsigliato).

Aggiornamento del file: calendario ufficiale su bls.gov/schedule
(NFP, CPI, PCE) e federalreserve.gov/newsevents (FOMC).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

MACRO_EVENTS_FILE = Path(__file__).resolve().parent.parent / "data" / "macro_events.json"
WARN_DAYS_AHEAD = 1  # badge mostrato se l'evento è oggi o domani


@dataclass
class MacroEvent:
    name: str
    event_date: date
    label: str


def _load_macro_events() -> list[MacroEvent]:
    if not MACRO_EVENTS_FILE.exists():
        return []
    try:
        raw = json.loads(MACRO_EVENTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    events = []
    for item in raw:
        try:
            events.append(MacroEvent(
                name=item["name"],
                event_date=date.fromisoformat(item["date"]),
                label=item.get("label", item["name"]),
            ))
        except Exception:
            continue
    return events


def get_macro_badges(today: Optional[date] = None) -> list[str]:
    """Lista di badge da mostrare come st.warning() in cima alla pagina."""
    today = today or datetime.now().date()
    badges = []
    for ev in _load_macro_events():
        delta = (ev.event_date - today).days
        if delta == 0:
            badges.append(f"⚠️ {ev.name} oggi — {ev.label}: evitare ingressi impulsivi pre-rilascio.")
        elif 0 < delta <= WARN_DAYS_AHEAD:
            badges.append(f"⚠️ {ev.name} tra {delta}gg — {ev.label}.")
    return badges
