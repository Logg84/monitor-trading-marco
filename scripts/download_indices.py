"""
Aggiorna i costituenti dei 5 indici monitorati.

Logica:
1. fonte ufficiale / ETF provider
2. fonte secondaria affidabile
3. Wikipedia
4. fallback statico solo se non esiste alcun file precedente

Le liste sono pensate per essere aggiornate al massimo mensilmente.
Se il file esiste già ed è più recente di max_age_days (default 30),
lo script non scarica nulla, salvo --force.
"""

from __future__ import annotations

import argparse
import re
import time
from io import BytesIO, StringIO
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
INDICES_DIR = ROOT / "data" / "indices"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:130.0) "
        "Gecko/20100101 Firefox/130.0"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

NASDAQ_HEADERS = {
    **HEADERS,
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/",
}

KNOWN_SUFFIXES = (
    ".AS",
    ".BR",
    ".DE",
    ".L",
    ".MC",
    ".MI",
    ".PA",
    ".ST",
    ".SW",
)


# ---------------------------------------------------------------------
# Fallback statici
#
# Sono usati SOLO se:
# - tutte le fonti online falliscono
# - non esiste già un CSV precedente
#
# Non devono essere la fonte normale.
# ---------------------------------------------------------------------

FALLBACK_SP500 = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "BRK-B", "LLY", "AVGO",
    "JPM", "V", "UNH", "XOM", "MA", "PG", "JNJ", "HD", "CVX", "MRK",
    "ABBV", "PEP", "COST", "WMT", "BAC", "KO", "TMO", "MCD", "CSCO", "ACN",
    "ABT", "DHR", "LIN", "CRM", "ADBE", "PFE", "NKE", "ORCL", "NOW", "CAT",
    "DIS", "PM", "IBM", "RTX", "GE", "HON", "AMAT", "VRTX", "BKNG", "LRCX",
    "UNP", "SPGI", "BLK", "LOW", "ISRG", "SYK", "PLD", "ADI", "MDLZ", "GILD",
    "REGN", "CB", "ETN", "MO", "BMY", "TGT", "DE", "CI", "SO", "MMC",
    "ZTS", "LMT", "C", "PYPL", "CL", "GS", "AMGN", "INTU", "TXN", "QCOM",
    "T", "VZ", "NEE", "SCHW", "AXP", "F", "GM", "BA", "MS", "WFC",
    "UPS", "ELV", "BSX", "TJX", "PGR", "ICE", "CME", "MCO", "MSCI", "SNPS",
]

FALLBACK_NASDAQ100 = [
    "AAPL", "ABNB", "ADBE", "ADI", "ADP", "AEP", "AMAT", "AMD", "AMGN", "AMZN",
    "ANSS", "APP", "ARM", "ASML", "AVGO", "AXON", "AZN", "BIIB", "BKNG", "BKR",
    "CCEP", "CDNS", "CDW", "CEG", "CHTR", "CMCSA", "COST", "CPRT", "CRWD", "CSCO",
    "CSGP", "CSX", "CTAS", "CTSH", "DASH", "DDOG", "DXCM", "EA", "EBAY", "ENPH",
    "EXC", "FANG", "FAST", "FLEX", "FTNT", "GEHC", "GFS", "GILD", "GOOG", "GOOGL",
    "IDXX", "ILMN", "INTC", "INTU", "ISRG", "KDP", "KHC", "KLAC", "LRCX", "LULU",
    "MAR", "MDB", "MDLZ", "MELI", "META", "MNST", "MRVL", "MSFT", "MU", "NFLX",
    "NTES", "NVDA", "NXPI", "ODFL", "OKTA", "ON", "ORLY", "PANW", "PAYX", "PDD",
    "PEP", "PYPL", "QCOM", "REGN", "RIVN", "ROST", "SBUX", "SIRI", "SMCI", "SNPS",
    "TEAM", "TMUS", "TSLA", "TTD", "TTWO", "TXN", "VRSK", "WBA", "WBD", "WDAY",
    "WDC", "XEL", "ZS",
]

FALLBACK_DAX = [
    "ALV.DE", "AIR.DE", "BAS.DE", "BAYN.DE", "BEI.DE", "BMW.DE", "BNT.DE", "CBK.DE",
    "CON.DE", "1COV.DE", "DTG.DE", "DB1.DE", "DBK.DE", "DHL.DE", "DTE.DE", "EOAN.DE",
    "ENR.DE", "FRE.DE", "FME.DE", "HEI.DE", "HNR1.DE", "HEN3.DE", "IFX.DE", "LIN.DE",
    "MBG.DE", "MRK.DE", "MTX.DE", "MUV2.DE", "P911.DE", "PUM.DE", "RHM.DE", "RWE.DE",
    "SAP.DE", "SRT3.DE", "SIE.DE", "SHL.DE", "SY1.DE", "VNA.DE", "VOW3.DE", "ZAL.DE",
]

FALLBACK_CAC40 = [
    "AC.PA", "AI.PA", "AIR.PA", "ALO.PA", "MT.AS", "CS.PA", "BNP.PA", "EN.PA",
    "CAP.PA", "CA.PA", "ACA.PA", "BN.PA", "DSY.PA", "EL.PA", "KER.PA", "LR.PA",
    "MC.PA", "ML.PA", "ORA.PA", "RI.PA", "PUB.PA", "RNO.PA", "SAF.PA", "SGO.PA",
    "SAN.PA", "SU.PA", "GLE.PA", "SW.PA", "STM.PA", "TEP.PA", "TTE.PA", "VIE.PA",
    "DG.PA", "EDEN.PA", "ERF.PA", "VIV.PA", "FTI.PA",
]

FALLBACK_FTSE100 = [
    "III.L", "ABF.L", "ADM.L", "AAL.L", "ANTO.L", "AZN.L", "AUTO.L", "BA.L",
    "BARC.L", "BDEV.L", "BP.L", "BT-A.L", "BNZL.L", "CCH.L", "CPG.L", "CRDA.L",
    "DGE.L", "EDV.L", "ENT.L", "EXPN.L", "FRES.L", "GLEN.L", "GSK.L", "HLMA.L",
    "HSBA.L", "IMB.L", "INF.L", "IAG.L", "ITV.L", "JD.L", "KGF.L", "LGEN.L",
    "LLOY.L", "LSEG.L", "MNDI.L", "NG.L", "NWG.L", "NXT.L", "OCDO.L", "PRU.L",
    "PSN.L", "RIO.L", "RKT.L", "REL.L", "RMV.L", "RR.L", "RMS.L", "SHEL.L",
    "SBRY.L", "SN.L", "SSE.L", "STAN.L", "STJ.L", "SVT.L", "TSCO.L", "ULVR.L",
    "UU.L", "VOD.L", "WPP.L",
]


# ---------------------------------------------------------------------
# Configurazione fonti
# ---------------------------------------------------------------------

INDICES = {
    "SP500": {
        "suffix": "",
        "min_count": 400,
        "fallback": FALLBACK_SP500,
        "attempts": [
            (
                "ssga_excel",
                "https://www.ssga.com/us/en/intermediary/etfs/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx",
            ),
            (
                "ishares",
                "https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf/1467271812596.ajax?fileType=csv&fileName=IVV_holdings",
            ),
            (
                "csv",
                "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv",
            ),
            (
                "csv",
                "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv",
            ),
            (
                "wiki",
                "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            ),
        ],
    },
    "NASDAQ100": {
        "suffix": "",
        "min_count": 90,
        "fallback": FALLBACK_NASDAQ100,
        "attempts": [
            (
                "nasdaq_api",
                "https://api.nasdaq.com/api/quote/list-type/nasdaq100",
            ),
            (
                "ishares",
                "https://www.ishares.com/us/products/239710/ishares-nasdaq-100-etf/1467271812596.ajax?fileType=csv&fileName=QQQ_holdings",
            ),
            (
                "csv",
                "https://raw.githubusercontent.com/datasets/nasdaq-100/main/data/constituents.csv",
            ),
            (
                "csv",
                "https://raw.githubusercontent.com/datasets/nasdaq-100/master/data/constituents.csv",
            ),
            (
                "wiki",
                "https://en.wikipedia.org/wiki/Nasdaq-100",
            ),
        ],
    },
    "FTSE100": {
        "suffix": ".L",
        "min_count": 80,
        "fallback": FALLBACK_FTSE100,
        "attempts": [
            (
                "ishares",
                "https://www.ishares.com/uk/individual/investor/en/products/251881/ishares-core-ftse-100-ucits-etf/1467271812596.ajax?fileType=csv&fileName=ISF_holdings",
            ),
            (
                "wiki",
                "https://en.wikipedia.org/wiki/FTSE_100_Index",
            ),
        ],
    },
    "DAX": {
        "suffix": ".DE",
        "min_count": 35,
        "fallback": FALLBACK_DAX,
        "attempts": [
            (
                "ishares",
                "https://www.ishares.com/de/privatanleger/en/products/251882/ishares-core-dax-ucits-etf-de/1467271812596.ajax?fileType=csv&fileName=EXIC_holdings",
            ),
            (
                "wiki",
                "https://en.wikipedia.org/wiki/DAX",
            ),
        ],
    },
    "CAC40": {
        "suffix": ".PA",
        "min_count": 30,
        "fallback": FALLBACK_CAC40,
        "attempts": [
            (
                "ishares",
                "https://www.ishares.com/fr/particulier/fr/products/251880/ishares-cac-40-ucits-etf-fr/1467271812596.ajax?fileType=csv&fileName=CAC_holdings",
            ),
            (
                "wiki",
                "https://en.wikipedia.org/wiki/CAC_40",
            ),
        ],
    },
}


# ---------------------------------------------------------------------
# Utility ticker
# ---------------------------------------------------------------------

def _clean(value: object, suffix: str) -> str | None:
    """
    Pulisce un ticker grezzo.

    Regole:
    - rimuove spazi, note, caratteri spurî
    - converte BRK.B in BRK-B per ticker USA
    - aggiunge il suffisso exchange se mancante
    - non aggiunge suffissi se il ticker ha già un suffisso noto
    """
    if value is None:
        return None

    v = str(value).strip().upper()

    # Rimuove note tipo [1], [2], ecc.
    v = re.sub(r"\[\d+\]", "", v)

    # Normalizza separatori tipo SAP:DE -> SAP.DE
    v = v.replace(":", ".")
    v = v.replace("/", "-")

    # Rimuove spazi e caratteri non ammessi
    v = re.sub(r"\s+", "", v)
    v = re.sub(r"[^A-Z0-9.\-]+", "", v)

    if not v or len(v) > 15:
        return None

    # Se il ticker ha già un suffisso exchange noto, lo lasciamo così.
    if any(v.endswith(s) for s in KNOWN_SUFFIXES):
        return v

    if suffix == "":
        # Per ticker USA: BRK.B -> BRK-B
        return v.replace(".", "-")

    if not v.endswith(suffix):
        v += suffix

    return v


def _tickers_from_dataframe(df: pd.DataFrame, suffix: str) -> list[str] | None:
    """Estrae ticker da un DataFrame cercando colonne tipo Symbol/Ticker."""
    if df is None or df.empty:
        return None

    col = None
    for c in df.columns:
        lc = str(c).strip().lower()
        if lc in {"symbol", "ticker"} or "ticker" in lc or "symbol" in lc:
            col = c
            break

    if col is None:
        return None

    out = [_clean(x, suffix) for x in df[col].dropna().tolist()]
    out = [x for x in out if x]

    if not out:
        return None

    return sorted(set(out))


# ---------------------------------------------------------------------
# Parser fonti
# ---------------------------------------------------------------------

def _from_csv_text(text: str, suffix: str) -> list[str] | None:
    """Parser CSV generico."""
    try:
        df = pd.read_csv(StringIO(text), sep=None, engine="python")
    except Exception:
        return None

    tickers = _tickers_from_dataframe(df, suffix)
    if tickers and len(tickers) >= 10:
        return tickers

    return None


def _from_ishares(text: str, suffix: str) -> list[str] | None:
    """
    Parser CSV iShares.

    I file iShares spesso hanno righe di metadata prima della tabella.
    Cerchiamo la riga che inizia con 'Ticker,'.
    """
    lines = text.splitlines()

    for i, line in enumerate(lines):
        if line.strip().lower().startswith("ticker,"):
            chunk = "\n".join(lines[i:])
            try:
                df = pd.read_csv(StringIO(chunk), sep=None, engine="python")
            except Exception:
                continue

            tickers = _tickers_from_dataframe(df, suffix)
            if tickers and len(tickers) >= 10:
                return tickers

    # Fallback: prova a leggerlo come CSV semplice
    return _from_csv_text(text, suffix)


def _from_excel_bytes(data: bytes, suffix: str) -> list[str] | None:
    """
    Parser Excel per file ufficiali tipo SPY/SSGA.

    Cerca nei primi 30 righi una riga di intestazione con Symbol/Ticker.
    """
    try:
        xls = pd.ExcelFile(BytesIO(data), engine="openpyxl")
    except Exception:
        return None

    for sheet in xls.sheet_names:
        try:
            raw = pd.read_excel(xls, sheet_name=sheet, header=None)
        except Exception:
            continue

        if raw.empty:
            continue

        limit = min(30, len(raw))
        for row_i in range(limit):
            row = [str(x).strip().lower() for x in raw.iloc[row_i].tolist()]
            if any(x in ("symbol", "ticker") for x in row):
                try:
                    df = pd.read_excel(xls, sheet_name=sheet, header=row_i)
                except Exception:
                    continue

                tickers = _tickers_from_dataframe(df, suffix)
                if tickers and len(tickers) >= 10:
                    return tickers

    return None


def _looks_like_rows(values: object) -> bool:
    """Capisce se una lista JSON sembra una lista di righe con ticker."""
    if not isinstance(values, list) or not values:
        return False

    first = values[0]
    if not isinstance(first, dict):
        return False

    keys = {str(k).lower() for k in first.keys()}
    return any(
        k in {"symbol", "ticker"} or "symbol" in k or "ticker" in k
        for k in keys
    )


def _find_rows(obj: object) -> list | None:
    """Ricerca ricorsiva di una lista di righe JSON plausibile."""
    if isinstance(obj, dict):
        for value in obj.values():
            if _looks_like_rows(value):
                return value
            found = _find_rows(value)
            if found is not None:
                return found

    elif isinstance(obj, list):
        for item in obj:
            if _looks_like_rows(item):
                return item
            found = _find_rows(item)
            if found is not None:
                return found

    return None


def _from_nasdaq_api(url: str, suffix: str) -> list[str] | None:
    """Parser API ufficiale Nasdaq per NASDAQ-100."""
    try:
        r = requests.get(url, headers=NASDAQ_HEADERS, timeout=30)
        r.raise_for_status()
        payload = r.json()
    except Exception:
        return None

    rows = None

    # Percorsi JSON più probabili
    for path in (
        ("data", "table", "rows"),
        ("data", "rows"),
        ("data", "table", "data"),
        ("data", "data"),
        ("data", "table", "dataset"),
    ):
        node = payload
        for key in path:
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                node = None
                break

        if isinstance(node, list):
            rows = node
            break

    if rows is None:
        rows = _find_rows(payload)

    if not rows:
        return None

    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue

        value = (
            row.get("symbol")
            or row.get("ticker")
            or row.get("Symbol")
            or row.get("Ticker")
        )

        if value:
            t = _clean(value, suffix)
            if t:
                out.append(t)

    out = sorted(set(out))
    if len(out) >= 10:
        return out

    return None


def _from_wiki(url: str, suffix: str) -> list[str] | None:
    """Parser Wikipedia con User-Agent browser."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        tables = pd.read_html(StringIO(r.text))
    except Exception:
        return None

    for tbl in tables:
        tickers = _tickers_from_dataframe(tbl, suffix)
        if tickers and len(tickers) >= 10:
            return tickers

    return None


# ---------------------------------------------------------------------
# Fetch pipeline
# ---------------------------------------------------------------------

def fetch_attempt(kind: str, url: str, suffix: str) -> list[str] | None:
    """Esegue un tentativo di download/parsing."""
    if kind == "wiki":
        return _from_wiki(url, suffix)

    if kind == "nasdaq_api":
        return _from_nasdaq_api(url, suffix)

    if kind == "ssga_excel":
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return _from_excel_bytes(r.content, suffix)

    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()

    if kind == "ishares":
        return _from_ishares(r.text, suffix)

    if kind == "csv":
        return _from_csv_text(r.text, suffix)

    if kind == "excel":
        return _from_excel_bytes(r.content, suffix)

    raise ValueError(f"Tipo fonte non riconosciuto: {kind}")


def fetch_index(cfg: dict) -> tuple[list[str] | None, str | None]:
    """Prova tutte le fonti configurate per un indice."""
    suffix = cfg["suffix"]
    min_count = cfg["min_count"]

    for kind, url in cfg["attempts"]:
        try:
            tickers = fetch_attempt(kind, url, suffix)
        except Exception as exc:
            print(f"  [{kind}] errore: {exc}")
            time.sleep(0.35)
            continue

        if tickers and len(tickers) >= min_count:
            return sorted(set(tickers)), kind

        if tickers:
            print(f"  [{kind}] scartato: {len(tickers)} ticker < {min_count}")

        time.sleep(0.35)

    return None, None


# ---------------------------------------------------------------------
# Persistenza e controllo età file
# ---------------------------------------------------------------------

def _file_age_days(path: Path) -> float:
    """Età del file in giorni. Se manca o sembra vuoto, ritorna valore alto."""
    try:
        if not path.exists():
            return 9999.0
        if path.stat().st_size < 20:
            return 9999.0
        return (time.time() - path.stat().st_mtime) / 86400.0
    except Exception:
        return 9999.0


def write_tickers(path: Path, tickers: list[str]) -> None:
    """Scrive il CSV nel formato compatibile con data_engine.py."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"Ticker": tickers}).to_csv(path, index=False)


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Aggiorna i costituenti degli indici con logica mensile."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Forza l'aggiornamento anche se il file è recente",
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=30,
        help="Età massima del file prima di tentare un aggiornamento (default 30)",
    )
    parser.add_argument(
        "--index",
        choices=sorted(INDICES.keys()),
        help="Aggiorna solo un indice specifico",
    )
    args = parser.parse_args()

    INDICES_DIR.mkdir(parents=True, exist_ok=True)

    names = [args.index] if args.index else list(INDICES.keys())

    for name in names:
        cfg = INDICES[name]
        path = INDICES_DIR / f"{name}.csv"
        age = _file_age_days(path)

        if path.exists() and not args.force and age <= args.max_age_days:
            print(f"{name}: skip, file aggiornato ({age:.0f} giorni)")
            continue

        if path.exists():
            print(f"{name}: file esistente vecchio di {age:.0f} giorni, provo aggiornamento")
        else:
            print(f"{name}: file mancante, provo download")

        tickers, source = fetch_index(cfg)

        if tickers:
            write_tickers(path, tickers)
            print(f"{name}: {len(tickers)} ticker da {source}")
            continue

        if path.exists():
            print(f"{name}: aggiornamento fallito, mantengo {path.name} esistente")
            continue

        fallback = [_clean(t, cfg["suffix"]) for t in cfg.get("fallback", [])]
        fallback = sorted({t for t in fallback if t})

        if fallback:
            write_tickers(path, fallback)
            print(f"{name}: {len(fallback)} ticker da fallback statico")
        else:
            print(f"{name}: nessuna fonte disponibile e nessun fallback, file non creato")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
