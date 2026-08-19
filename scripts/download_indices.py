"""
Aggiorna i costituenti dei 5 indici.
Catena: ETF iShares → GitHub dataset → Wikipedia → lista statica (fallback).
"""
import sys
from pathlib import Path
from io import StringIO

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import requests

from core.data_engine import INDICES_DIR

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:130.0) "
                   "Gecko/20100101 Firefox/130.0"),
}

# Fallback statico: NASDAQ-100 principali ticker (2026-08).
# Se TUTTO fallisce, non restiamo mai senza dati.
FALLBACK_NASDAQ100 = [
    "AAPL", "MSFT", "AMZN", "NVDA", "META", "GOOGL", "GOOG", "TSLA",
    "AVGO", "COST", "NFLX", "AMD", "PEP", "LIN", "TMUS", "CSCO",
    "ADBE", "QCOM", "INTC", "INTU", "TXN", "CMCSA", "AMGN", "AMAT",
    "ISRG", "MU", "BKNG", "LRCX", "GILD", "VRTX", "ADI", "ADP",
    "SBUX", "MDLZ", "PANW", "KLAC", "REGN", "SNPS", "PYPL", "CDNS",
    "MAR", "ABNB", "CRWD", "ASML", "FTNT", "MELI", "ORLY", "MNST",
    "NXPI", "ROP", "CHTR", "AEP", "DASH", "PAYX", "CTSH", "PCAR",
    "ROST", "EXC", "KDP", "ODFL", "BKR", "EA", "VRSK", "FAST",
    "IDXX", "CTAS", "GEHC", "XEL", "KHC", "LULU", "CPRT", "BIIB",
    "CSX", "DDOG", "TEAM", "ZS", "WBD", "DXCM", "TTWO", "ANSS",
    "WDAY", "FANG", "ON", "ILMN", "MRVL", "DLTR", "WBA", "SPLK",
]

def _clean(v: str, suffix: str) -> str | None:
    v = v.strip().upper()
    if ":" in v:
        v = v.split(":")[-1]
    v = v.replace(" ", "")
    if not v or len(v) > 12:
        return None
    if suffix == "":
        return v.replace(".", "-")
    if not v.endswith(suffix):
        v += suffix
    return v

def _from_csv_text(text: str, suffix: str) -> list[str] | None:
    try:
        df = pd.read_csv(StringIO(text))
    except Exception:
        return None
    col = None
    for c in df.columns:
        if c.strip().lower() in ("symbol", "ticker"):
            col = c
            break
    if col is None:
        return None
    out = [t for t in (_clean(str(x), suffix) for x in df[col].dropna()) if t]
    return sorted(set(out)) if len(out) >= 10 else None

def _from_ishares(text: str, suffix: str) -> list[str] | None:
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.strip().lower().startswith("ticker,"):
            start = i
            break
    if start is None:
        return None
    try:
        df = pd.read_csv(StringIO("\n".join(lines[start:])))
    except Exception:
        return None
    out = [t for t in (_clean(str(x), suffix) for x in df["Ticker"].dropna()) if t]
    return sorted(set(out)) if len(out) >= 10 else None

def _from_wiki(url: str, suffix: str) -> list[str] | None:
    try:
        tables = pd.read_html(url, headers=HEADERS)
    except Exception:
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            tables = pd.read_html(StringIO(r.text))
        except Exception:
            return None
    for tbl in tables:
        col = None
        for c in tbl.columns:
            if str(c).strip().lower() in ("ticker", "symbol", "ticker symbol"):
                col = c
                break
        if col is None:
            continue
        out = [t for t in (_clean(str(x), suffix) for x in tbl[col].dropna()) if t]
        if len(out) >= 10:
            return sorted(set(out))
    return None

SOURCES = {
    "SP500": ([
        ("ishares", "https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf/1467271812596.ajax?fileType=csv&fileName=IVV_holdings"),
        ("github", "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"),
        ("github", "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv"),
        ("wiki", "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"),
    ], "", None),
    "NASDAQ100": ([
        ("ishares", "https://www.ishares.com/us/products/239710/ishares-nasdaq-100-etf/1467271812596.ajax?fileType=csv&fileName=QQQ_holdings"),
        ("github", "https://raw.githubusercontent.com/datasets/nasdaq-100/refs/heads/master/data/constituents.csv"),
        ("wiki", "https://en.wikipedia.org/wiki/Nasdaq-100"),
    ], "", FALLBACK_NASDAQ100),
    "FTSE100": ([
        ("wiki", "https://en.wikipedia.org/wiki/FTSE_100_Index"),
    ], ".L", None),
    "DAX": ([
        ("wiki", "https://en.wikipedia.org/wiki/DAX"),
    ], ".DE", None),
    "CAC40": ([
        ("wiki", "https://en.wikipedia.org/wiki/CAC_40"),
    ], ".PA", None),
}

def main() -> None:
    INDICES_DIR.mkdir(parents=True, exist_ok=True)
    for name, (attempts, suffix, fallback) in SOURCES.items():
        tickers = None
        for kind, url in attempts:
            try:
                if kind == "wiki":
                    tickers = _from_wiki(url, suffix)
                else:
                    r = requests.get(url, headers=HEADERS, timeout=30)
                    r.raise_for_status()
                    text = r.text
                    tickers = (_from_ishares(text, suffix) if kind == "ishares"
                               else _from_csv_text(text, suffix))
            except Exception as e:
                print(f"{name} [{kind}]: {e}")
                continue
            if tickers:
                print(f"{name}: {len(tickers)} ticker da {kind}")
                break

        if not tickers and fallback:
            tickers = [_clean(t, suffix) for t in fallback]
            tickers = [t for t in tickers if t]
            print(f"{name}: {len(tickers)} ticker da fallback statico")

        if not tickers:
            path = INDICES_DIR / f"{name}.csv"
            if path.exists():
                print(f"{name}: mantengo file precedente ({path.name})")
                continue
            print(f"{name}: NESSUNA fonte disponibile, file non creato")
            continue

        pd.DataFrame({"Ticker": tickers}).to_csv(INDICES_DIR / f"{name}.csv", index=False)

if __name__ == "__main__":
    main()