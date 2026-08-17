#!/usr/bin/env python3
"""
download_indices.py
-------------------
Scarica mensilmente le liste complete dei componenti di:
  - S&P 500     (SPY xlsx -> iShares IVV -> Wikipedia)
  - Nasdaq 100  (api.nasdaq.com -> Invesco QQQ -> Wikipedia)
  - DAX         (iShares EXIC -> Wikipedia)
  - CAC 40      (Wikipedia)
  - FTSE MIB    (Wikipedia)

Solo CSV/XLSX ETF + tabelle Wikipedia — niente parser PDF.
Salva su GitHub in `indices/` (filesystem Streamlit Cloud effimero).

Uso:
    python download_indices.py                # scarica tutto e push su GitHub
    python download_indices.py --only sp500   # solo un indice
    python download_indices.py --local        # test locale in ./output/

Dipendenze: pip install pandas requests openpyxl lxml
Variabili d'ambiente per il push: GITHUB_TOKEN, GITHUB_REPO
"""

import argparse
import base64
import io
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")
INDICES_DIR_GH = "indices"
OUTPUT_DIR_LOCAL = Path("./output")
NOW_ISO = datetime.now().isoformat(timespec="seconds")

HEADERS_BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def _save(df: pd.DataFrame, name: str, source: str, local_only: bool) -> pd.DataFrame:
    df = df.copy()
    df = df.dropna(subset=["ticker"])
    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
    df["index"] = name
    df["source"] = source
    df["fetched_at"] = NOW_ISO

    if local_only:
        OUTPUT_DIR_LOCAL.mkdir(exist_ok=True)
        path = OUTPUT_DIR_LOCAL / f"{name}.csv"
        df.to_csv(path, index=False)
        print(f"[OK] {name}: {len(df)} righe -> {path}  (fonte: {source})")
    else:
        gh_path = f"{INDICES_DIR_GH}/{name}.csv"
        if _commit_to_github(gh_path, df, f"Aggiorna {name} da download_indices.py"):
            print(f"[OK] {name}: {len(df)} righe -> {gh_path}  (fonte: {source})")
        else:
            print(f"[FAIL] {name}: commit su GitHub fallito")
    return df


def _commit_to_github(path: str, df: pd.DataFrame, message: str) -> bool:
    if not GITHUB_TOKEN or not GITHUB_REPO:
        print("[WARN] GITHUB_TOKEN o GITHUB_REPO mancanti, skip commit.")
        return False
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Content-Type": "application/json"}
    r = requests.get(url, headers=headers)
    sha = r.json().get("sha") if r.status_code == 200 else None
    content_b64 = base64.b64encode(df.to_csv(index=False).encode()).decode()
    payload = {"message": message, "content": content_b64, "branch": "main"}
    if sha:
        payload["sha"] = sha
    resp = requests.put(url, headers=headers, json=payload)
    if resp.status_code in (200, 201):
        return True
    print(f"[WARN] GitHub API -> {resp.status_code}: {resp.text[:200]}")
    return False


# ---------------------------------------------------------------------------
# WIKIPEDIA — fallback universale (tabelle costituenti)
# ---------------------------------------------------------------------------
WIKI_URLS = {
    "sp500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
    "nasdaq100": "https://en.wikipedia.org/wiki/Nasdaq-100",
    "dax": "https://en.wikipedia.org/wiki/DAX",
    "cac40": "https://en.wikipedia.org/wiki/CAC_40",
    "ftsemib": "https://en.wikipedia.org/wiki/FTSE_MIB",
}


def _find_col(columns, keys):
    for c in columns:
        cl = str(c).strip().lower()
        if any(k in cl for k in keys):
            return c
    return None


def get_wikipedia(name: str, local_only: bool, min_rows: int = 20) -> pd.DataFrame:
    url = WIKI_URLS[name]
    tables = pd.read_html(url)
    for t in tables:
        if t.shape[0] < min_rows:
            continue
        tc = _find_col(t.columns, ("ticker", "symbol", "mnemo"))
        nc = _find_col(t.columns, ("company", "security", "name", "constituent"))
        if not tc or not nc:
            continue
        out = pd.DataFrame({"ticker": t[tc].astype(str), "name": t[nc].astype(str)})
        out["ticker"] = (
            out["ticker"]
            .str.replace(r"^(BIT|EPA|XETR|FWB|SWX|NASDAQ|NYSE)\s*:\s*", "", regex=True)
            .str.strip()
            .str.upper()
        )
        out = out[out["ticker"].str.match(r"^[A-Z0-9][A-Z0-9.\-]*$", na=False)]
        if len(out) >= min_rows:
            return _save(out, name, f"Wikipedia ({url.rsplit('/', 1)[-1]})", local_only)
    raise ValueError(f"Nessuna tabella costituenti valida su {url}")


# ---------------------------------------------------------------------------
# S&P 500 — SPY xlsx -> iShares IVV -> Wikipedia
# ---------------------------------------------------------------------------
SPY_XLSX_URL = (
    "https://www.ssga.com/us/en/intermediary/etfs/library-content/products/"
    "fund-data/etfs/us/holdings-daily-us-en-spy.xlsx"
)
IVV_CSV_URL = (
    "https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf/"
    "1467271812596.ajax?fileType=csv&fileName=IVV_holdings&dataType=fund"
)


def get_sp500(local_only: bool) -> pd.DataFrame:
    try:
        r = requests.get(SPY_XLSX_URL, headers=HEADERS_BROWSER, timeout=30)
        r.raise_for_status()
        df = pd.read_excel(io.BytesIO(r.content), skiprows=4)
        df = df.rename(columns={"Ticker": "ticker", "Name": "name", "Weight": "weight"})
        df = df[df["ticker"].notna() & ~df["ticker"].astype(str).str.contains("Cash", case=False, na=False)]
        return _save(df[["ticker", "name", "weight"]], "sp500", "SPY holdings (SSGA)", local_only)
    except Exception as e:
        print(f"[WARN] SPY primario fallito ({e}), fallback IVV...")

    try:
        r = requests.get(IVV_CSV_URL, headers=HEADERS_BROWSER, timeout=30)
        r.raise_for_status()
        text = r.content.decode("utf-8", errors="ignore")
        header_idx = next(i for i, line in enumerate(text.splitlines()) if line.startswith("Ticker"))
        df = pd.read_csv(io.StringIO(text), skiprows=header_idx)
        df = df.rename(columns={"Ticker": "ticker", "Name": "name", "Weight (%)": "weight"})
        return _save(df[["ticker", "name", "weight"]].dropna(subset=["ticker"]), "sp500", "iShares IVV (fallback)", local_only)
    except Exception as e:
        print(f"[WARN] IVV fallito ({e}), fallback Wikipedia...")

    return get_wikipedia("sp500", local_only, min_rows=100)


# ---------------------------------------------------------------------------
# Nasdaq 100 — api.nasdaq.com -> Invesco QQQ -> Wikipedia
# ---------------------------------------------------------------------------
NASDAQ_API_URL = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"
QQQ_CSV_URL = (
    "https://www.invesco.com/us/financial_products/etfs/holdings/main/holdings/0"
    "?audienceType=Investor&action=download&ticker=QQQ"
)


def get_nasdaq100(local_only: bool) -> pd.DataFrame:
    try:
        r = requests.get(NASDAQ_API_URL, headers=HEADERS_BROWSER, timeout=30)
        r.raise_for_status()
        rows = r.json()["data"]["data"]["rows"]
        df = pd.DataFrame(rows)
        df = df.rename(columns={"symbol": "ticker", "companyName": "name", "marketCap": "market_cap"})
        return _save(df[["ticker", "name"]], "nasdaq100", "api.nasdaq.com (ufficiale)", local_only)
    except Exception as e:
        print(f"[WARN] API Nasdaq fallita ({e}), fallback QQQ...")

    try:
        r = requests.get(QQQ_CSV_URL, headers=HEADERS_BROWSER, timeout=30)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.content.decode("utf-8", errors="ignore")))
        df = df.rename(columns={"Holding Ticker": "ticker", "Name": "name", "Weight": "weight"})
        return _save(df[["ticker", "name"]].dropna(subset=["ticker"]), "nasdaq100", "Invesco QQQ (fallback)", local_only)
    except Exception as e:
        print(f"[WARN] QQQ fallito ({e}), fallback Wikipedia...")

    return get_wikipedia("nasdaq100", local_only, min_rows=50)


# ---------------------------------------------------------------------------
# DAX — iShares EXIC -> Wikipedia
# ---------------------------------------------------------------------------
DAX_CSV_URL = (
    "https://www.ishares.com/de/privatanleger/de/produkte/251464/"
    "ishares-core-dax-ucits-etf-de-fund/1478358465952.ajax"
    "?fileType=csv&fileName=EXXT_holdings&dataType=fund"
)


def get_dax(local_only: bool) -> pd.DataFrame:
    try:
        r = requests.get(DAX_CSV_URL, headers=HEADERS_BROWSER, timeout=30)
        r.raise_for_status()
        text = r.content.decode("utf-8", errors="ignore")
        header_idx = next(i for i, line in enumerate(text.splitlines()) if line.startswith("Ticker") or line.startswith("Name"))
        df = pd.read_csv(io.StringIO(text), skiprows=header_idx)
        df.columns = [c.strip() for c in df.columns]
        df = df.rename(columns={"Ticker": "ticker", "Name": "name", "Weight (%)": "weight"})
        return _save(df[["ticker", "name", "weight"]].dropna(subset=["ticker"]), "dax", "iShares Core DAX (EXIC)", local_only)
    except Exception as e:
        print(f"[WARN] iShares DAX fallito ({e}), fallback Wikipedia...")

    return get_wikipedia("dax", local_only, min_rows=30)


# ---------------------------------------------------------------------------
# CAC 40 — Wikipedia (URL Amundi non più disponibile)
# ---------------------------------------------------------------------------
def get_cac40(local_only: bool) -> pd.DataFrame:
    return get_wikipedia("cac40", local_only, min_rows=30)


# ---------------------------------------------------------------------------
# FTSE MIB — Wikipedia (URL Xtrackers non più disponibile)
# ---------------------------------------------------------------------------
def get_ftsemib(local_only: bool) -> pd.DataFrame:
    return get_wikipedia("ftsemib", local_only, min_rows=30)


FETCHERS = {
    "sp500": get_sp500,
    "nasdaq100": get_nasdaq100,
    "dax": get_dax,
    "cac40": get_cac40,
    "ftsemib": get_ftsemib,
}


def _build_combined(dfs: list[pd.DataFrame], local_only: bool):
    if not dfs:
        return
    combined = pd.concat(dfs, ignore_index=True)
    if local_only:
        OUTPUT_DIR_LOCAL.mkdir(exist_ok=True)
        path = OUTPUT_DIR_LOCAL / "all_indices.csv"
        combined.to_csv(path, index=False)
        print(f"[OK] Combinato: {path} ({len(combined)} righe)")
    else:
        gh_path = f"{INDICES_DIR_GH}/all_indices.csv"
        if _commit_to_github(gh_path, combined, "Aggiorna all_indices.csv (combinato mensile)"):
            print(f"[OK] Combinato su GitHub: {gh_path} ({len(combined)} righe)")
        else:
            print(f"[FAIL] Commit combinato fallito")


def main():
    parser = argparse.ArgumentParser(description="Download mensile componenti indici")
    parser.add_argument("--only", choices=list(FETCHERS.keys()), help="Scarica solo un indice")
    parser.add_argument("--local", action="store_true", help="Test locale in ./output/ (niente GitHub)")
    args = parser.parse_args()

    if not args.local and (not GITHUB_TOKEN or not GITHUB_REPO):
        print("[WARN] GITHUB_TOKEN/GITHUB_REPO mancanti, passo a modalità --local")
        args.local = True

    targets = [args.only] if args.only else list(FETCHERS.keys())
    all_dfs: list[pd.DataFrame] = []
    for name in targets:
        try:
            df = FETCHERS[name](local_only=args.local)
            all_dfs.append(df)
        except Exception as e:
            print(f"[ERRORE] {name}: {e}", file=sys.stderr)

    _build_combined(all_dfs, args.local)
    print(f"\n✓ Totale: {sum(len(df) for df in all_dfs)} ticker su {len(all_dfs)} indici")


if __name__ == "__main__":
    main()
