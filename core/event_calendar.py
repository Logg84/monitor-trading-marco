"""
Calendario eventi multi-settore.

Fonti con API pubblica gratuita:
  - ClinicalTrials.gov (Farmaceutico/biotech) — API v2, no key
  - SEC EDGAR (Estrattivo USA, tutti i settori) — RSS full-text
  - SAM.gov (Contratti federali, Aerospaziale/difesa) — API opps
  - NHTSA (Automotive/EV) — API recalls/ratings
  - USPTO PTAB (Brevetti) — API trial
  - FDA (Farmaceutico) — API event/enforcement

Ogni evento ha link diretto alla fonte ufficiale.
Gli eventi SENZA link verificabile non vengono mostrati.
"""
from __future__ import annotations

import datetime
import json
import os
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
EVENTS_DIR = DATA_DIR / "events"
EVENTS_PATH = EVENTS_DIR / "events.json"
LAST_CHECK_PATH = EVENTS_DIR / "last_check.json"

# ── Diagnostica per-fonte ────────────────────────────────────
# Ogni fetch_* registra qui l'esito reale (status HTTP, errore, conteggio),
# così in caso di "nessun evento" si vede SUBITO quale fonte ha fallito e
# perché, invece di indovinare — visibile nella pagina Calendario.
_last_diag: list[dict] = []


def _diag_reset() -> None:
    _last_diag.clear()


def _diag_log(fonte: str, status: str, dettaglio: str = "", count: int = 0) -> None:
    _last_diag.append({"fonte": fonte, "status": status,
                        "dettaglio": dettaglio, "count": count})


def get_last_diagnostics() -> list[dict]:
    """Diagnostica dell'ultimo fetch_all_events(): una riga per fonte."""
    return list(_last_diag)


# ── Schema evento ──────────────────────────────────────────
SETTORI = [
    "Farmaceutico/Biotech",
    "Estrattivo (Mining, Oil&Gas)",
    "Aerospaziale/Difesa",
    "Automotive/EV",
    "Legale/Brevetti",
    "Tecnologia/Semiconduttori",
]

# Mappa ticker/nome per le aziende più comuni seguite in screening.
# Sarà integrata con l'universo dello screening a runtime.

# ├─ Farmaceutico/biotech ────────────────────────────
PHARMA_TICKERS = {
    "PFE": "Pfizer", "JNJ": "Johnson & Johnson", "MRK": "Merck",
    "ABBV": "AbbVie", "BMY": "Bristol-Myers Squibb", "LLY": "Eli Lilly",
    "AMGN": "Amgen", "GILD": "Gilead Sciences", "BIIB": "Biogen",
    "REGN": "Regeneron", "VRTX": "Vertex", "MRNA": "Moderna",
    "BNTX": "BioNTech", "AZN.L": "AstraZeneca", "NOVN.SW": "Novartis",
    "ROG.SW": "Roche", "SNY": "Sanofi", "GSK.L": "GSK",
    "NVS": "Novartis ADR", "RHHVF": "Roche ADR",
}

# ├─ Estrattivo ───────────────────────────────────────
MINING_TICKERS = {
    "XOM": "Exxon Mobil", "CVX": "Chevron", "SHEL.L": "Shell",
    "TTE.PA": "TotalEnergies", "BP.L": "BP", "RDSB.L": "Shell (LSE)",
    "GLEN.L": "Glencore", "RIO.L": "Rio Tinto", "BHP.L": "BHP Group",
    "FCX": "Freeport-McMoRan", "NEM": "Newmont", "SCCO": "Southern Copper",
    "VALE": "Vale", "TTE": "TotalEnergies ADR",
}

# ├─ Aerospaziale/difesa ─────────────────────────────
AERO_TICKERS = {
    "BA": "Boeing", "LMT": "Lockheed Martin", "RTX": "Raytheon",
    "NOC": "Northrop Grumman", "GD": "General Dynamics",
    "EADSY": "Airbus ADR", "AIR.PA": "Airbus",
    "SAIC": "Science Applications", "LHX": "L3Harris",
    "HII": "Huntington Ingalls",
}

# ├─ Automotive/EV ───────────────────────────────────
AUTO_TICKERS = {
    "TSLA": "Tesla", "F": "Ford", "GM": "General Motors",
    "STLA": "Stellantis", "VWAGY": "Volkswagen ADR",
    "BMW.DE": "BMW", "MBG.DE": "Mercedes-Benz",
    "RIVN": "Rivian", "LCID": "Lucid", "NIO": "NIO",
    "BYD.DE": "BYD", "HMC": "Honda",
}


def load_events() -> list[dict]:
    if EVENTS_PATH.exists():
        try:
            return json.loads(EVENTS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_events(events: list[dict]) -> None:
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    EVENTS_PATH.write_text(
        json.dumps(events, indent=2, ensure_ascii=False), encoding="utf-8")


def save_check_log(log_entry: dict) -> None:
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    logs = []
    if LAST_CHECK_PATH.exists():
        try:
            logs = json.loads(LAST_CHECK_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    logs.append(log_entry)
    logs = logs[-30:]
    LAST_CHECK_PATH.write_text(
        json.dumps(logs, indent=2, ensure_ascii=False), encoding="utf-8")


def _map_ticker(s: str, search: str) -> str | None:
    """Cerca un ticker in una delle mappe per nome azienda."""
    s_low = s.lower()
    for ticker, nome in {**PHARMA_TICKERS, **MINING_TICKERS,
                         **AERO_TICKERS, **AUTO_TICKERS}.items():
        if search.lower() in nome.lower():
            return ticker
    for ticker, nome in {**PHARMA_TICKERS, **MINING_TICKERS,
                         **AERO_TICKERS, **AUTO_TICKERS}.items():
        if search.lower() in s_low or s_low in search.lower():
            return ticker
    return None


# ════════════════════════════════════════════════════════════
# CLINICALTRIALS.GOV — API v2 pubblica (nessuna chiave)
# ════════════════════════════════════════════════════════════
CT_BASE = "https://clinicaltrials.gov/api/v2/studies"


def _search_ct(sponsor_terms: list[str], max_studies: int = 10) -> list[dict]:
    """
    Cerca studi in ClinicalTrials.gov per sponsor.
    Filtra: studi in corso con completamento primario atteso.
    """
    # AREA[SponsorName] non è un nome di area valido nella sintassi essie di
    # CT.gov (l'API tornava HTTP 400 "Unknown area name: SponsorName").
    # Il nome corretto è LeadSponsorName, coerente con il campo
    # sponsorCollaboratorsModule.leadSponsor usato nel parsing sotto.
    query = "(" + " OR ".join(f'AREA[LeadSponsorName]"{t}"' for t in sponsor_terms) + ")"
    params = {
        # query.spons cerca sul nome sponsor. query.cond (usato prima) cerca
        # sulla condizione medica: con nomi di azienda restituiva sempre
        # zero risultati.
        "query.spons": query,
        "filter.overallStatus": "RECRUITING|ACTIVE_NOT_RECRUITING",
        # "filter.primaryCompletionDate" non esiste nell'API v2 documentata:
        # la richiesta tornava 400 e la funzione andava in return [] silenzioso.
        # Il filtro sulla data viene fatto lato client più sotto.
        "pageSize": str(max_studies),
        "fields": "NCTId,BriefTitle,Phase,PrimaryCompletionDate,OverallStatus,LeadSponsorName,Condition",
        "format": "json",
    }
    try:
        r = requests.get(CT_BASE, params=params, timeout=30)
        if r.status_code != 200:
            _diag_log("ClinicalTrials.gov", f"HTTP {r.status_code}", r.text[:200])
            return []
        data = r.json()
        studies = data.get("studies", [])[:max_studies]
        _diag_log("ClinicalTrials.gov", "OK", count=len(studies))
        return studies
    except Exception as ex:
        _diag_log("ClinicalTrials.gov", "ECCEZIONE", str(ex)[:200])
        return []


def fetch_ct_events(max_per_sponsor: int = 5) -> list[dict]:
    """
    Recupera eventi da ClinicalTrials.gov per i principali sponsor farmaceutici.
    Ogni evento ha link diretto NCT.
    """
    events = []
    now = datetime.datetime.now(datetime.UTC).isoformat()

    # Principali sponsor farmaceutici in portafoglio screening
    sponsors = [
        "Pfizer", "Merck", "Johnson & Johnson", "AbbVie",
        "Bristol-Myers Squibb", "Eli Lilly", "Amgen", "Gilead Sciences",
        "Biogen", "Regeneron", "Vertex", "Moderna", "BioNTech",
        "AstraZeneca", "Novartis", "Roche", "Sanofi", "GSK",
    ]

    # Contatori per la diagnostica interna al parsing (separati dallo status
    # HTTP, che _search_ct già logga): quanti studi trovati vs quanti
    # scartati per data mancante/passata, per non dover più indovinare
    # se il problema è "zero risultati dall'API" o "risultati scartati qui".
    n_trovati = 0
    n_senza_data = 0
    n_passati = 0
    n_ok = 0

    for batch in [sponsors[i:i + 5] for i in range(0, len(sponsors), 5)]:
        studies = _search_ct(batch, max_studies=max_per_sponsor)
        n_trovati += len(studies)
        for study in studies[:max_per_sponsor]:
            protocol = study.get("protocolSection", {})

            nct_id = protocol.get("identificationModule", {}).get("nctId")
            if not nct_id:
                continue

            # Corretto: briefTitle vive in identificationModule, non in
            # descriptionModule (che in v2 contiene detailedDescription).
            desc = protocol.get("identificationModule", {}).get("briefTitle", "—")

            # Corretto: il lead sponsor vive in sponsorCollaboratorsModule,
            # non in un modulo "sponsor" (che non esiste in questo schema).
            sponsor_name = protocol.get("sponsorCollaboratorsModule", {}) \
                                    .get("leadSponsor", {}) \
                                    .get("name", "—")

            phase = protocol.get("designModule", {}).get("phases", ["—"])[0]
            cond = protocol.get("conditionsModule", {}).get("conditions", ["—"])[0]

            # Corretto: il campo si chiama primaryCompletionDateStruct
            # (con sotto-chiavi "date" e "type": ESTIMATED/ACTUAL), non
            # primaryCompletionDate. Con il nome sbagliato questa lookup
            # restituiva sempre None e OGNI studio veniva scartato dal
            # "continue" sotto — la causa reale per cui il calendario
            # mostrava solo eventi passati (le altre fonti attive sono
            # tutte "orientamento: passato" per costruzione).
            pc_date = protocol.get("statusModule", {}) \
                               .get("primaryCompletionDateStruct", {}) \
                               .get("date")
            if not pc_date:
                n_senza_data += 1
                continue

            # Filtro data lato client (prima delegato a un parametro API
            # inesistente): tiene solo i trial con completamento non ancora
            # passato. pc_date può essere "YYYY-MM" oltre a "YYYY-MM-DD".
            try:
                pc_check = pc_date if len(pc_date) > 7 else pc_date + "-01"
                if datetime.date.fromisoformat(pc_check) < datetime.date.today():
                    n_passati += 1
                    continue
            except ValueError:
                n_senza_data += 1
                continue

            n_ok += 1
            ticker = _map_ticker(sponsor_name.lower(), sponsor_name)
            events.append({
                "ticker": ticker or sponsor_name,
                "nome": sponsor_name,
                "settore": "Farmaceutico/Biotech",
                "tipo": f"Risultati Fase {phase}",
                "descrizione": desc[:120],
                "data_attesa": pc_date,
                # ClinicalTrials.gov riporta una stima dello sponsor: slitta spesso.
                # Non va mai presentata come data certa.
                "stato_data": "stimata",
                "link_ufficiale": f"https://clinicaltrials.gov/study/{nct_id}",
                "ultimo_controllo": now,
                "fonte": "ClinicalTrials.gov",
                "nct_id": nct_id,
                "verified": True,
                "orientamento": "futuro",
            })
        time.sleep(0.5)

    # Diagnostica del parsing, separata da quella HTTP già loggata in
    # _search_ct: se in futuro un campo cambia ancora nome, questa riga
    # lo mostra subito invece di dover dedurlo dal sintomo "solo passati".
    _diag_log(
        "ClinicalTrials.gov (parsing)", "OK",
        f"trovati={n_trovati} senza_data={n_senza_data} scartati_perché_passati={n_passati} inclusi={n_ok}",
        count=n_ok,
    )

    return events


# ════════════════════════════════════════════════════════════
# SEC EDGAR — RSS full-text per 8-K/10-K (depositi regolatori)
# ════════════════════════════════════════════════════════════
SEC_SEARCH = "https://efts.sec.gov/LATEST/search-index"
SEC_CIK = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={}&type=8-K&dateb=&owner=exclude&output=atom"


def _cik_for_ticker(ticker: str) -> str | None:
    """Ricava CIK da ticker via SEC EDGAR index."""
    try:
        r = requests.get(
            "https://efts.sec.gov/LATEST/search-index",
            params={"q": f"ticker:{ticker}", "dateRange": "all",
                    "startdt": "1900-01-01", "enddt": "2099-12-31"},
            headers={"User-Agent": "MonitorTrading/1.0 (research)",
                     "Accept": "application/json"},
            timeout=15
        )
        if r.status_code == 200:
            data = r.json()
            hits = data.get("hits", {}).get("hits", [])
            if hits:
                cik = hits[0].get("_source", {}).get("cik")
                if cik:
                    return str(cik).zfill(10)
    except Exception:
        pass
    return None


SEC_TICKERS = {
    **PHARMA_TICKERS, **MINING_TICKERS,
    **AERO_TICKERS, **AUTO_TICKERS,
}


def fetch_sec_events(max_per_ticker: int = 3) -> list[dict]:
    """
    Recupera eventi SEC EDGAR 8-K per i ticker dello screening.
    Link diretto al deposito EDGAR.
    """
    events = []
    now = datetime.datetime.now(datetime.UTC).isoformat()
    tickers_sample = list(SEC_TICKERS.keys())[:20]

    for ticker in tickers_sample:
        cik = _cik_for_ticker(ticker)
        if not cik:
            continue
        try:
            url = SEC_CIK.format(cik)
            r = requests.get(
                url,
                headers={"User-Agent": "MonitorTrading/1.0 (research)"},
                timeout=20
            )
            if r.status_code != 200:
                continue
            try:
                root = ET.fromstring(r.content)
                ns = {"atom": "http://www.w3.org/2005/Atom",
                      "sec": "http://www.sec.gov/disclosures"}
                entries = root.findall("atom:entry", ns)[:max_per_ticker]
                for entry in entries:
                    title_el = entry.find("atom:title", ns)
                    title = title_el.text if title_el is not None else "—"
                    link_el = entry.find("atom:link", ns)
                    href = link_el.get("href") if link_el is not None else ""
                    updated_el = entry.find("atom:updated", ns)
                    date_str = updated_el.text[:10] if updated_el is not None else ""
                    if not href or not date_str:
                        continue
                    content_el = entry.find("atom:summary", ns)
                    summary = content_el.text[:200] if content_el is not None else "—"
                    events.append({
                        "ticker": ticker,
                        "nome": SEC_TICKERS[ticker],
                        "settore": "Estrattivo (Mining, Oil&Gas)"
                        if ticker in MINING_TICKERS
                        else "Farmaceutico/Biotech" if ticker in PHARMA_TICKERS
                        else "Aerospaziale/Difesa" if ticker in AERO_TICKERS
                        else "Automotive/EV",
                        "tipo": "Deposito 8-K (già avvenuto)",
                        "descrizione": title,
                        "data_attesa": date_str,  # data del deposito, non un evento futuro
                        "stato_data": "confermata",
                        "link_ufficiale": href,
                        "ultimo_controllo": now,
                        "fonte": "SEC EDGAR",
                        "nct_id": None,
                        "verified": True,
                        "orientamento": "passato",
                    })
            except ET.ParseError:
                continue
        except Exception:
            continue
        time.sleep(0.3)
    return events


# ════════════════════════════════════════════════════════════
# SAM.GOV — Contratti federali opps (API pubblica)
# ════════════════════════════════════════════════════════════
SAM_API = "https://api.sam.gov/opportunities/v2/search"


def fetch_sam_events(max_results: int = 10, api_key: str | None = None) -> list[dict]:
    """
    Recupera contratti federali da SAM.gov per aziende aerospaziali/difesa.
    Richiede api_key gratuita da SAM.gov se disponibile.
    Senza API key restituisce lista vuota.
    """
    api_key = api_key or os.environ.get("SAM_API_KEY") or ""
    if not api_key:
        _diag_log("SAM.gov", "SALTATA", "nessuna API key fornita")
        return []

    events = []
    now = datetime.datetime.now(datetime.UTC).isoformat()
    try:
        params = {
            "api_key": api_key,
            "limit": max_results,
            "naics": "3364",  # Aerospace Product & Parts
        }
        r = requests.get(SAM_API, params=params, timeout=30)
        if r.status_code != 200:
            _diag_log("SAM.gov", f"HTTP {r.status_code}", r.text[:200])
            return []
        data = r.json()
        for opp in data.get("opps", [])[:max_results]:
            title = opp.get("title", "—")
            agency = opp.get("departmentName", "—")
            posted = opp.get("postedDate", "")[:10]
            response = opp.get("responseDate", "")[:10]
            date = response or posted
            link = f"https://sam.gov/opp/{opp.get('oppId', '')}/view"
            if not link or not date:
                continue
            events.append({
                "ticker": None,
                "nome": agency,
                "settore": "Aerospaziale/Difesa",
                # Scadenza di offerta, non assegnazione: l'assegnazione avviene dopo.
                "tipo": "Scadenza gara federale",
                "descrizione": title[:120],
                "data_attesa": date,
                "stato_data": "confermata",
                "link_ufficiale": link,
                "ultimo_controllo": now,
                "fonte": "SAM.gov",
                "nct_id": None,
                "verified": True,
                "orientamento": "futuro",
            })
        _diag_log("SAM.gov", "OK", count=len(events))
    except Exception as ex:
        _diag_log("SAM.gov", "ECCEZIONE", str(ex)[:200])
    return events


# ════════════════════════════════════════════════════════════
# NHTSA — Recall/Certification API (pubblica)
# ════════════════════════════════════════════════════════════
NHTSA_RECALLS = "https://api.nhtsa.gov/recall/recallsByManufacturer"


def fetch_nhtsa_events(max_per_mfr: int = 5) -> list[dict]:
    """
    DISATTIVATA — non chiamata da fetch_all_events.
    L'endpoint usato qui sotto ("recall/recallsByManufacturer") non esiste
    nell'API ufficiale NHTSA. L'unico endpoint recall documentato è
    "recalls/recallsByVehicle" (plurale), che richiede make+model+modelYear
    specifici — non esiste un endpoint "tutti i richiami di un produttore".
    Interrogare per ogni modello/anno di ogni casa auto sarebbe possibile
    ma richiederebbe centinaia di chiamate per popolare il calendario,
    troppo oneroso per il beneficio (i richiami sono comunque eventi
    passati, non fanno parte del calendario "in arrivo").
    Lasciata nel codice come riferimento, non rimossa, nel caso in futuro
    si trovi un dataset bulk NHTSA più adatto da integrare diversamente.
    """
    events = []
    now = datetime.datetime.now(datetime.UTC).isoformat()
    manufacturers = [
        "Tesla", "Ford", "General Motors", "Stellantis",
        "Volkswagen", "BMW", "Mercedes-Benz", "Rivian",
        "Lucid", "NIO", "Honda",
    ]
    for mfr in manufacturers:
        try:
            r = requests.get(
                f"{NHTSA_RECALLS}?manufacturer={mfr}",
                headers={"User-Agent": "MonitorTrading/1.0"},
                timeout=15
            )
            if r.status_code != 200:
                continue
            data = r.json()
            results = data.get("results", [])[:max_per_mfr]
            for rec in results:
                desc = rec.get("summary", "—")[:150]
                date = rec.get("reportReceivedDate", "")[:10]
                nhtsa_id = rec.get("nhtsaCampaignNumber", "")
                if not nhtsa_id or not date:
                    continue
                link = f"https://www.nhtsa.gov/recall?nhtsaId={nhtsa_id}"
                events.append({
                    "ticker": next((
                        t for t, n in AUTO_TICKERS.items()
                        if mfr.lower() in n.lower()
                    ), mfr),
                    "nome": mfr,
                    "settore": "Automotive/EV",
                    "tipo": "Richiamo NHTSA (già avvenuto)",
                    "descrizione": desc,
                    "data_attesa": date,  # data di ricezione, non un evento futuro
                    "stato_data": "confermata",
                    "link_ufficiale": link,
                    "ultimo_controllo": now,
                    "fonte": "NHTSA",
                    "nct_id": None,
                    "verified": True,
                    "orientamento": "passato",
                })
        except Exception:
            continue
    return events


# ════════════════════════════════════════════════════════════
# FDA — Approvazioni / Eventi regolatori
# ════════════════════════════════════════════════════════════
# FDA API: https://open.fda.gov/apis/drug/event/
# Richiede API key (gratuita) per uso regolatorio strutturato.
# Senza key, forniamo solo una indicazione di dove trovare i dati.


def fetch_fda_events(api_key: str | None = None, max_results: int = 5) -> list[dict]:
    """
    Recupera segnalazioni di farmacovigilanza (FAERS) da open.fda.gov.

    ATTENZIONE — questo NON è un calendario di decisioni regolatorie:
    l'endpoint drug/event.json restituisce segnalazioni di eventi avversi
    già ricevute dalla FDA, non le date di decisione PDUFA (approvazione/
    rigetto) che erano l'obiettivo originale di questa integrazione.
    La FDA non pubblica le date PDUFA tramite API strutturata gratuita:
    per quelle serve consultare manualmente il calendario su fda.gov,
    oppure un aggregatore di settore (da NON usare come fonte primaria
    per il link ufficiale, si veda nota generale del modulo).

    Richiede API key gratuita. Senza, restituisce lista vuota.
    """
    api_key = api_key or os.environ.get("FDA_API_KEY") or ""
    if not api_key:
        _diag_log("FDA (FAERS)", "SALTATA", "nessuna API key fornita")
        return []

    events = []
    now = datetime.datetime.now(datetime.UTC).isoformat()
    manufacturers = [
        "Pfizer", "Merck", "Johnson & Johnson", "AbbVie",
        "Eli Lilly", "Amgen", "Gilead", "Roche", "Novartis",
    ]

    n_http_errori = 0
    n_ok_risposte = 0
    try:
        for mfr in manufacturers:
            # I nomi multi-parola (es. "Johnson & Johnson", "Eli Lilly") vanno
            # tra virgolette nella sintassi di ricerca openFDA, altrimenti
            # spazi e "&" producono una query malformata.
            params = {
                "api_key": api_key,
                "search": f'patient.drug.openfda.manufacturer_name:"{mfr}"',
                # Senza sort, openFDA restituisce i risultati nell'ordine
                # del suo indice interno — spesso segnalazioni di anni fa.
                # Ordinando per receiptdate decrescente si ottengono le
                # segnalazioni più recenti, molto più utili nel contesto
                # di questo calendario.
                "sort": "receiptdate:desc",
                "limit": max_results,
            }
            # openFDA espone un endpoint GET con parametri in query string,
            # non POST con corpo JSON: la chiamata precedente falliva sempre
            # (status diverso da 200), azzerando silenziosamente i risultati.
            r = requests.get(
                "https://api.fda.gov/drug/event.json",
                params=params, timeout=20
            )
            if r.status_code != 200:
                n_http_errori += 1
                _diag_log("FDA (FAERS)", f"HTTP {r.status_code} su '{mfr}'", r.text[:200])
                continue
            n_ok_risposte += 1
            data = r.json()
            for result in data.get("results", [])[:max_results]:
                drug = result.get("patient", {}).get("drug", [{}])[0]
                drug_name = drug.get("medicinalproduct", "—")
                reaction = result.get("patient", {}).get("reaction", [{}])[0]
                reac = reaction.get("reactionmeddrapt", "—")
                # openFDA restituisce receiptdate come "YYYYMMDD" senza
                # separatori (es. "20140312"): [:10] non lo converte,
                # lascia la stringa grezza. Va riformattato in ISO.
                raw_date = result.get("receiptdate", "")
                if len(raw_date) == 8 and raw_date.isdigit():
                    date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
                else:
                    date = raw_date[:10]
                if not date:
                    continue
                events.append({
                    "ticker": next((
                        t for t, n in PHARMA_TICKERS.items()
                        if mfr.lower() in n.lower()
                    ), mfr),
                    "nome": mfr,
                    "settore": "Farmaceutico/Biotech",
                    "tipo": "Segnalazione farmacovigilanza (FAERS)",
                    "descrizione": f"{drug_name}: {reac}",
                    "data_attesa": date,  # data di ricezione segnalazione, non decisione futura
                    "stato_data": "confermata",
                    "link_ufficiale": "https://open.fda.gov/apis/drug/event/",
                    "ultimo_controllo": now,
                    "fonte": "FDA (FAERS)",
                    "nct_id": None,
                    "verified": True,
                    "orientamento": "passato",
                })
    except Exception as ex:
        _diag_log("FDA (FAERS)", "ECCEZIONE", str(ex)[:200])
        return events

    _diag_log(
        "FDA (FAERS)", "OK" if events else "NESSUN RISULTATO",
        f"risposte_200={n_ok_risposte} errori_http={n_http_errori} su {len(manufacturers)} produttori",
        count=len(events),
    )
    return events


# ════════════════════════════════════════════════════════════
# USPTO PTAB — Controversie brevettuali (API pubblica)
# ════════════════════════════════════════════════════════════
PTAB_API = "https://developer.uspto.gov/ptab-api/v1/"


def _ptab_search(search: str, max_results: int = 5) -> list[dict]:
    try:
        r = requests.get(
            f"{PTAB_API}cases",
            params={"q": search, "limit": max_results, "order": "-filingDate"},
            headers={"User-Agent": "MonitorTrading/1.0"},
            timeout=20,
        )
        if r.status_code == 200:
            return r.json().get("results", [])[:max_results]
    except Exception:
        pass
    return []


PTAB_TICKERS = {
    "AAPL": "Apple", "GOOGL": "Alphabet", "MSFT": "Microsoft",
    "META": "Meta", "AMZN": "Amazon", "NVDA": "NVIDIA",
    "INTC": "Intel", "AMD": "AMD", "QCOM": "Qualcomm",
    "CRM": "Salesforce", "ORCL": "Oracle", "IBM": "IBM",
    "TSLA": "Tesla", "BA": "Boeing", "LMT": "Lockheed Martin",
}


def fetch_ptab_events(max_results: int = 10) -> list[dict]:
    """
    Recupera decisioni PTAB per controversie brevettuali recenti
    che coinvolgono aziende tech/farmaceutiche.
    """
    events = []
    now = datetime.datetime.now(datetime.UTC).isoformat()
    for ticker in list(PTAB_TICKERS.keys())[:8]:
        results = _ptab_search(f"\"{PTAB_TICKERS[ticker]}\"", max_results=2)
        for case in results:
            title = case.get("titleOfInvention", "—")[:120]
            proseq = case.get("proceedingStatus", "—")
            filing = case.get("filingDate", "")[:10]
            case_id = case.get("caseId", "")
            if not case_id:
                continue
            events.append({
                "ticker": ticker,
                "nome": PTAB_TICKERS[ticker],
                "settore": "Legale/Brevetti",
                "tipo": f"PTAB {proseq} (deposito già avvenuto)",
                "descrizione": f"Controversia brevetto: {title}",
                "data_attesa": filing,  # data di deposito, non l'esito futuro della causa
                "stato_data": "confermata",
                "link_ufficiale": f"https://developer.uspto.gov/ptab-api/v1/cases/{case_id}",
                "ultimo_controllo": now,
                "fonte": "USPTO PTAB",
                "nct_id": None,
                "verified": True,
                "orientamento": "passato",
            })
        time.sleep(0.3)
    return events


# ════════════════════════════════════════════════════════════
# TECNOLOGIA — Nessuna fonte regolatoria strutturata.
# I dati per questo settore vengono marcati come "annuncio aziendale"
# e trattati separatamente nelle UI.
# ════════════════════════════════════════════════════════════


def fetch_all_events(sam_key: str | None = None,
                     fda_key: str | None = None) -> list[dict]:
    """
    Fetch eventi da TUTTE le fonti.
    Ogni evento ha link_ufficiale verificabile.

    NOTA: solo ClinicalTrials.gov e SAM.gov producono eventi genuinamente
    futuri ("orientamento": "futuro"). Le altre fonti attive (SEC, FDA/FAERS,
    PTAB) restituiscono depositi/segnalazioni già avvenuti, utili come
    cronologia/conferma ma non come calendario di eventi in arrivo — vanno
    mostrati nella UI in una sezione separata, non tra i "prossimi eventi".
    NHTSA è disattivata (vedi fetch_nhtsa_events).
    """
    events = []
    _diag_reset()

    events += fetch_ct_events()
    events += fetch_sec_events()
    events += fetch_sam_events(api_key=sam_key)
    # NHTSA disattivata: l'endpoint "recallsByManufacturer" non esiste
    # nell'API ufficiale (che espone solo "recallsByVehicle", richiede
    # make+model+modelYear specifici e non un elenco per produttore).
    # Vedi fetch_nhtsa_events() più sotto per i dettagli.
    # events += fetch_nhtsa_events()
    events += fetch_fda_events(api_key=fda_key)
    events += fetch_ptab_events()

    events.sort(key=lambda e: e.get("data_attesa", "9999-99-99"))
    return events


# ════════════════════════════════════════════════════════════
# INTEGRAZIONE ALERT
# ════════════════════════════════════════════════════════════

def check_upcoming_events(days_ahead: int = 14) -> list[dict]:
    """
    Confronta gli eventi salvati con la data odierna.
    Se un evento ha data_attesa tra oggi e oggi+days_ahead
    ED è genuinamente futuro (orientamento == "futuro"),
    viene restituito per invio alert.

    Eventi con orientamento "passato" (depositi, richiami, segnalazioni
    già avvenuti) sono esclusi qui: il loro alert non avrebbe senso,
    dato che l'evento è già accaduto quando li recuperiamo.
    """
    events = load_events()
    today = datetime.date.today()
    alert_window = today + datetime.timedelta(days=days_ahead)

    upcoming = []
    for e in events:
        if e.get("orientamento") != "futuro":
            continue
        try:
            d = datetime.date.fromisoformat(e["data_attesa"])
            if today <= d <= alert_window:
                upcoming.append(e)
        except Exception:
            continue
    return upcoming


def build_alert_text(ticker_data: dict, ticker: str = "") -> str:
    ticker = ticker or ticker_data.get("ticker") or "—"
    return (
        f"📅 **EVENTO IN SCADENZA**\n"
        f"`{ticker}` · {ticker_data.get('nome', '—')}\n"
        f"{ticker_data.get('settore', '—')} — {ticker_data.get('tipo', '—')}\n"
        f"Data: {ticker_data.get('data_attesa', '—')}\n"
        f"{ticker_data.get('descrizione', '—')}\n"
        f"Fonte: {ticker_data.get('fonte', '—')}\n"
        f"🔗 {ticker_data.get('link_ufficiale', '—')}"
    )
