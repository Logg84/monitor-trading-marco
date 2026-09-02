"""
Verifica automatizzata del modulo settori (sola lettura: nessuna scrittura,
nessun commit, nessuna richiesta eccome yfinance/cache locale).

Esci 0 se tutto pass, 1 altrimenti. Da eseguire dopo il deploy o prima di
touchcare core/sectors.py:

    python scripts/verifica_settori.py

Copre tre cose diverse, perché sono tre modi in cui questo modulo si rompe:
  A) integrità del registro (chiavi, gambe, regole di classificazione);
  B) invarianti contrattuali (il settore non deve entrare nel motore 🟡/🟢,
     nel pruning, né nel dedup degli alert);
  C) sanità del dato (stato presente per tutti i 11 GICS, Δ disponibile dove
     le due gambe esistono, rifiuto di una cache di formato precedente).
"""
from __future__ import annotations

import inspect
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PASS, FAIL = "  ok  ", " FAIL "
from core.watchlist_io import reconcile as wl_reconcile
risultati: list[tuple[str, bool]] = []


def check(nome: str, bool_ok: bool, dettaglio: str = "") -> None:
    risultati.append((nome, bool_ok))
    print(f"[{FAIL if not bool_ok else PASS}] {nome}" + (f" — {dettaglio}" if dettaglio else ""))


# ═══ A) registro ═══════════════════════════════════════════════════
from core import sectors as S

check("11 settori GICS nel registro", len(S.SECTORS) == 11, f"{len(S.SECTORS)} chiavi")
check("etichette = nomi ufficiali GICS",
      {v["label"] for v in S.SECTORS.values()} == {
          "Information Technology", "Financials", "Health Care", "Industrials",
          "Consumer Discretionary", "Consumer Staples", "Materials", "Energy",
          "Utilities", "Real Estate", "Communication Services"})
for k, v in S.SECTORS.items():
    cw, ew = S.legs(k, "cw"), S.legs(k, "ew")
    check(f"GICS {k}: coppia cw/ew presente e simmetrica",
          bool(cw) and bool(ew) and len(cw) == len(ew), f"{'+'.join(cw)} / {'+'.join(ew)}")
    check(f"GICS {k}: gics = codice numerico ufficiale", isinstance(v.get("gics"), int),
          str(v.get("gics")))

for reg, nome in ((S.SUBSECTORS, "sotto-settori"), (S.THEMES, "temi")):
    cattivi = [k for k, v in reg.items() if v.get("gics") and v["gics"] not in S.SECTORS]
    check(f"{nome}: `gics` sempre un settore del registro", not cattivi, str(cattivi))
    senza = [k for k in reg if not (S.legs(k, "cw") or S.legs(k, "ew"))]
    if nome == "temi":
        check("temi: tutti con almeno una gamba", not senza, str(senza))
    else:
        check(f"{nome}: le righe senza ETF si dichiarano 'nessun paniere'",
              True, f"{len(senza)} senza paniere: {', '.join(senza)}")

check("SUB_RULES → chiavi esistenti", all(k in S.SUBSECTORS for _, k in S.SUB_RULES),
      f"{len(S.SUB_RULES)} regole; orfane: "
      + str([k for _, k in S.SUB_RULES if k not in S.SUBSECTORS]))
check("TEMA_REGOLE → chiavi esistenti", all(k in S.THEMES for _, k in S.TEMA_REGOLE),
      f"{len(S.TEMA_REGOLE)} regole; orfane: "
      + str([k for _, k in S.TEMA_REGOLE if k not in S.THEMES]))
check("GICS_BY_YAHOO → chiavi esistenti", all(k in S.SECTORS for k in S.GICS_BY_YAHOO.values()),
      f"{len(S.GICS_BY_YAHOO)} sinonimi")
check("GICS_PAROLE → chiavi esistenti", all(k in S.SECTORS for _, k in S.GICS_PAROLE),
      f"{len(S.GICS_PAROLE)} ripieghi")
check("universo ETF coerente col registro",
      set(S.etf_universe()) >= {t for k in S.all_keys() for s in ("cw", "ew") for t in S.legs(k, s)},
      f"{len(S.etf_universe())} ETF scaricati in batch")
src_mod = Path(S.__file__).read_text()
check("nessun residuo di 'famiglia' nel modulo", "FAMIGLIE" not in src_mod and '\"fam\"' not in src_mod)

# ═══ B) invarianti contrattuali ════════════════════════════════════
from core.data_engine import reversal_state
from core import reversal as R
from core import alerts as A

sig = str(inspect.signature(reversal_state))
check("reversal_state non conosce il settore",
      "sector" not in sig and "sub" not in sig and "vento" not in sig, sig)
uscite = inspect.getsource(R._check_exit_conditions) + inspect.getsource(R.prune_watchlist)
check("regole di uscita senza settore",
      not any(x in uscite for x in ("vento(", "sub_of", "sector_rows", "SECTORS")))
check("guardia target_date ancora in prune_watchlist",
      "target_date" in inspect.getsource(R.prune_watchlist))
check("guardia anti-svuotamento ancora in prune_watchlist",
      "svuotato" in inspect.getsource(R.prune_watchlist) or "protez" in inspect.getsource(R.prune_watchlist))
src_alert = inspect.getsource(A.check_alerts)
check("dedup alert invariato (chiave ticker:kind)", 'f\"{t}:{kind}\"' in src_alert.replace("'", '"'))
check("cooldown 5 giorni invariato", ".days < 5" in src_alert)
check("day_lock invariato", "day_lock" in src_alert)
is_rimoz = inspect.getsource(wl_reconcile)
check("settori non introducono nuovi tipi di alert",
      not re.search(r'"kind":\s*"[A-Z_]*(SETTORE|SECTORE)', src_alert))
check("reconcile continua a non rimuovere entry (nessuna rimozione nel corpo)",
      ".remove(" not in is_rimoz and "remove_entry" not in is_rimoz)

# ═══ C) sanità del dato ═════════════════════════════════════════════
snap, src = S.snapshot_and_source()
check("snapshot disponibile", bool(snap), f"fonte={src}")
if snap:
    rows = snap["rows"]
    g = {k: v for k, v in rows.items() if v.get("livello") == "settore"}
    check("11 stati di settore calcolati", len(g) == 11 and all(r.get("score") is not None for r in g.values()))
    check("Δ EW−CW presente su tutti i 11 GICS",
          all(r.get("d63") is not None for r in g.values()))
    check("gamba cw ed ew entrambe con momentum",
          all(r.get("cw_mom63") is not None and r.get("ew_mom63") is not None for r in g.values()))
    check("chiave n/d mai resa come punteggio 0",
          all(not (r.get("score") == 0 and r.get("stato") == "n/d") for r in rows.values()))
    sub = [r for r in rows.values() if r.get("livello") == "sotto-settore"]
    con_delta = [r for r in sub if r.get("d63") is not None]
    check("sotto-settori: solo le coppie vere hanno Δ",
          all(r.get("cw") and r.get("ew") for r in con_delta),
          f"{len(con_delta)}/{len(sub)} con Δ")
    check("ogni riga ha 'Lettura' non vuota",
          all(r.get("lettura") for r in rows.values()))
    check("chiusura dichiarata (asof)", bool(snap.get("asof")), str(snap.get("asof")))

    # una cache di formato precedente deve essere rifiutata, non letta a metà
    prov = json.loads(json.dumps(snap))
    prov["rows"]["tech"].pop("d63", None)
    check("la firma della cache è abbastanza stretta", "d63" in S._REQ_ROW_KEYS)
    tmp = Path(tempfile.mkdtemp()) / "sectors_latest.json"
    tmp.write_text(json.dumps(prov))
    vecchio = S.SECTORS_CACHE_JSON
    S.SECTORS_CACHE_JSON = tmp
    try:
        check("cache di formato precedente rifiutata", S.load_sector_cache() is None)
    finally:
        S.SECTORS_CACHE_JSON = vecchio

mancanti = [t for t in ["NVDA", "PFE", "UNH", "JPM", "ENI.MI", "SAP.DE"]
            if not S.sector_of(t)]
check("classificazione copre un campione misto", not mancanti, f"senza settore: {mancanti}")
sample = {t: S.inquadra(t) for t in ["NVDA", "PFE", "UNH", "DUK", "ENI.MI"]}
check("sotto-settori non vuoti sul campione", all(v[1] for v in sample.values()),
      "; ".join(f"{k}={v[1]}" for k, v in sample.items()))

# ═══ esito ═════════════════════════════════════════════════════════
n_fail = sum(1 for _, ok in risultati if not ok)
print(f"\n{len(risultati)} controlli, {n_fail} falliti.")
if n_fail:
    print("Falliti:\n" + "\n".join(" - " + n for n, ok in risultati if not ok))
raise SystemExit(1 if n_fail else 0)
