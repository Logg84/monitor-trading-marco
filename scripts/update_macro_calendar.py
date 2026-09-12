"""
scripts/update_macro_calendar.py

Aggiorna automaticamente data/macro_events.json con le prossime date di:

  - NFP (Employment Situation) e CPI: dal feed iCalendar UFFICIALE del BLS
    (bls.gov/schedule/news_release/bls.ics). Fonte primaria, formato
    stabile (VEVENT con DTSTART+SUMMARY), niente scraping HTML fragile.

  - FOMC: la Fed non pubblica un feed strutturato equivalente, quindi si fa
    un parsing leggero della pagina calendario ufficiale
    (federalreserve.gov/monetarypolicy/fomccalendars.htm). Più fragile del
    feed BLS per costruzione: se il parsing fallisce o non trova nulla, lo
    script NON cancella le date FOMC già presenti nel file — le lascia
    invariate e segnala l'errore in output, per non passare silenziosamente
    da un calendario aggiornato a uno stale o vuoto.

Uso: python scripts/update_macro_calendar.py
Pensato per girare una volta al mese da GitHub Actions (vedi
.github/workflows/macro_calendar.yml).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

import requests

MACRO_EVENTS_FILE = Path(__file__).resolve().parent.parent / "data" / "macro_events.json"
BLS_ICS_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
FOMC_CALENDAR_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"

MONTH_ABBR = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def _fetch(url: str, timeout: int = 20) -> str:
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": "monitor-trading-marco/1.0"})
    resp.raise_for_status()
    return resp.text


def parse_bls_ics(ics_text: str, oggi: date) -> list[dict]:
    """Estrae le prossime date di Employment Situation (NFP) e Consumer
    Price Index (CPI) dal feed iCalendar ufficiale del BLS."""
    events = []
    for block in ics_text.split("BEGIN:VEVENT")[1:]:
        m_date = re.search(r"DTSTART[^:]*:(\d{8})T", block)
        m_summary = re.search(r"SUMMARY:(.+)", block)
        if not (m_date and m_summary):
            continue
        try:
            d = datetime.strptime(m_date.group(1), "%Y%m%d").date()
        except ValueError:
            continue
        if d < oggi:
            continue
        summary = m_summary.group(1).strip()
        if summary == "Employment Situation":
            events.append({"name": "NFP", "date": d.isoformat(), "label": "Employment Situation (BLS)"})
        elif summary == "Consumer Price Index":
            events.append({"name": "CPI", "date": d.isoformat(), "label": "Consumer Price Index (BLS)"})
    return events


def parse_fomc_calendar(html: str, oggi: date) -> list[date]:
    """
    Parsing best-effort della pagina calendario FOMC (nessun feed
    strutturato disponibile, a differenza del BLS). Due passate:
    1) Date CONFERMATE dai link agli statement già pubblicati
       ('monetaryYYYYMMDDa1.pdf'): esatte al giorno, prese direttamente
       dall'URL invece che dal testo della tabella.
    2) Riunioni future ancora senza statement: dal testo
       '**MeseIntestazione**' seguito dal range 'DD-DD' nella sezione
       dell'anno corrente/prossimo. Esclude i "notation vote" (non sono
       riunioni con decisione delle 14:00, non generano volatilità
       comparabile).
    Non solleva mai eccezioni sui singoli match: un pattern imprevisto
    viene scartato, non l'intero parsing.
    """
    dates: set[date] = set()

    for ymd in re.findall(r"monetary(\d{8})a1\.pdf", html):
        try:
            d = datetime.strptime(ymd, "%Y%m%d").date()
        except ValueError:
            continue
        if d >= oggi:
            dates.add(d)

    for year in (oggi.year, oggi.year + 1):
        m_section = re.search(rf"#### {year} FOMC Meetings(.*?)(?:\n#### |\Z)", html, re.S)
        if not m_section:
            continue
        section = m_section.group(1)
        pattern = re.compile(
            r"\*\*([A-Za-z]+)(?:/([A-Za-z]+))?\*\*\s*\n+\s*(\d{1,2})(?:-(\d{1,2}))?"
            r"(?!\s*\(notation)"
        )
        for m in pattern.finditer(section):
            mese1, mese2, d1, d2 = m.groups()
            mese_fine = mese2 or mese1
            giorno_fine = int(d2) if d2 else int(d1)
            mnum = MONTH_ABBR.get(mese_fine[:3])
            if not mnum:
                continue
            try:
                d = date(year, mnum, giorno_fine)
            except ValueError:
                continue
            if d >= oggi:
                dates.add(d)

    return sorted(dates)


def main() -> int:
    oggi = date.today()
    existing = []
    if MACRO_EVENTS_FILE.exists():
        try:
            existing = json.loads(MACRO_EVENTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    existing_fomc = [e for e in existing if e.get("name") == "FOMC" and e.get("date", "") >= oggi.isoformat()]

    errors = []

    try:
        bls_events = parse_bls_ics(_fetch(BLS_ICS_URL), oggi)
        if not bls_events:
            raise ValueError("nessuna data NFP/CPI futura trovata nel feed")
    except Exception as e:
        bls_events = [e for e in existing if e.get("name") in ("NFP", "CPI") and e.get("date", "") >= oggi.isoformat()]
        errors.append(f"BLS: {e} (mantengo le {len(bls_events)} date già presenti)")

    try:
        fomc_dates = parse_fomc_calendar(_fetch(FOMC_CALENDAR_URL), oggi)
        if not fomc_dates:
            raise ValueError("parsing riuscito ma nessuna data futura trovata")
        fomc_events = [{"name": "FOMC", "date": d.isoformat(), "label": "Decisione tassi Fed (FOMC)"} for d in fomc_dates]
    except Exception as e:
        fomc_events = existing_fomc
        errors.append(f"FOMC: {e} (mantengo le {len(existing_fomc)} date già presenti)")

    all_events = sorted(bls_events + fomc_events, key=lambda e: e["date"])
    MACRO_EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    MACRO_EVENTS_FILE.write_text(json.dumps(all_events, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Scritte {len(all_events)} date ({len(bls_events)} NFP/CPI da BLS, {len(fomc_events)} FOMC).")
    if errors:
        # Non un'eccezione fatale: se anche solo una delle due fonti ha dato
        # dati freschi, li scriviamo comunque. L'errore resta visibile nel
        # log del workflow (Actions -> macro-calendar-monthly) per capire
        # cosa non ha funzionato, senza bloccare il commit dei dati buoni.
        print("ATTENZIONE:", " | ".join(errors))
    return 0


if __name__ == "__main__":
    sys.exit(main())
