#!/usr/bin/env python3
"""
download_indices.py
-------------------
Scarica mensilmente le liste complete dei componenti di:
  - S&P 500     (SPY xlsx | fallback iShares IVV)
  - Nasdaq 100  (api.nasdaq.com | fallback Invesco QQQ)
  - DAX         (iShares Core DAX ETF)
  - CAC 40      (Amundi CAC 40 ETF)
  - FTSE MIB    (Xtrackers FTSE MIB ETF)

Solo CSV/XLSX da ETF ufficiali — niente parser PDF.
Salva direttamente su GitHub in `indices/` (filesystem Streamlit Cloud effimero).

Uso:
    python download_indices.py                # scarica tutto e push su GitHub
    python download_indices.py --only sp500   # solo un indice
    python download_indices.py --local        # test locale in ./output/

Variabili d'ambiente:
    GITHUB_TOKEN, GITHUB_REPO (già presenti in secrets)
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
# S&P 500 — primario: SPDR SPY xlsx | fallback: iShares IVV CSV
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
        print(f"[WARN] SPY primario fallito ({e}), fallback iShares IVV...")

    r = requests.get(IVV_CSV_URL, headers=HEADERS_BROWSER, timeout=30)
    r.raise_for_status()
    text = r.content.decode("utf-8", errors="ignore")
    header_idx = next(i for i, line in enumerate(text.splitlines()) if line.startswith("Ticker"))
    df = pd.read_csv(io.StringIO(text), skiprows=header_idx)
    df = df.rename(columns={"Ticker": "ticker", "Name": "name", "Weight (%)": "weight"})
    return _save(df[["ticker", "name", "weight"]].dropna(subset=["ticker"]), "sp500", "iShares IVV holdings (fallback)", local_only)


# ---------------------------------------------------------------------------
# Nasdaq 100 — primario: api.nasdaq.com | fallback: Invesco QQQ CSV
# ---------------------------------------------------------------------------
NASDAQ_API_URL = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"
QQQ_CSV_URL = (
    "https://www.invesco.com/us/financial-products/etfs/holdings/main/holdings/0"
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
        print(f"[WARN] API Nasdaq fallita ({e}), fallback Invesco QQQ...")

    r = requests.get(QQQ_CSV_URL, headers=HEADERS_BROWSER, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.content.decode("utf-8", errors="ignore")))
    df = df.rename(columns={"Holding Ticker": "ticker", "Name": "name", "Weight": "weight"})
    return _save(df[["ticker", "name"]].dropna(subset=["ticker"]), "nasdaq100", "Invesco QQQ holdings (fallback)", local_only)


# ---------------------------------------------------------------------------
# DAX — iShares Core DAX ETF (EXIC)
# ---------------------------------------------------------------------------
DAX_CSV_URL = (
    "https://www.ishares.com/de/privatanleger/de/produkte/251464/"
    "ishares-core-dax-ucits-etf-de-fund/1478358465952.ajax"
    "?fileType=csv&fileName=EXXT_holdings&dataType=fund"
)


def get_dax(local_only: bool) -> pd.DataFrame:
    r = requests.get(DAX_CSV_URL, headers=HEADERS_BROWSER, timeout=30)
    r.raise_for_status()
    text = r.content.decode("utf-8", errors="ignore")
    header_idx = next(i for i, line in enumerate(text.splitlines()) if line.startswith("Ticker") or line.startswith("Name"))
    df = pd.read_csv(io.StringIO(text), skiprows=header_idx)
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns={"Ticker": "ticker", "Name": "name", "Weight (%)": "weight"})
    return _save(df[["ticker", "name", "weight"]].dropna(subset=["ticker"]), "dax", "iShares Core DAX (EXIC) holdings", local_only)


# ---------------------------------------------------------------------------
# CAC 40 — Amundi CAC 40 ETF
# ---------------------------------------------------------------------------
CAC40_ETF_CSV_URL = "https://www.amundietf.it/it/professional/produkte/etf/amundi-cac-40-ucits-etf-dist/FR0007052782/download-holdings"


def get_cac40(local_only: bool) -> pd.DataFrame:
    r = requests.get(CAC40_ETF_CSV_URL, headers=HEADERS_BROWSER, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.content.decode("utf-8", errors="ignore")))
    df.columns = [c.strip() for c in df.columns]
    rename_map = {}
    for col in df.columns:
        cl = col.lower()
        if cl in ("ticker", "mnemo", "symbol"):
            rename_map[col] = "ticker"
        elif cl in ("name", "company"):
            rename_map[col] = "name"
        elif cl in ("weight", "weight (%)"):
            rename_map[col] = "weight"
    df = df.rename(columns=rename_map)
    if "name" not in df.columns:
        df["name"] = ""
    if "weight" not in df.columns:
        df["weight"] = None
    out = df[["ticker", "name", "weight"]].dropna(subset=["ticker"])
    return _save(out, "cac40", "Amundi CAC 40 ETF holdings", local_only)


# ---------------------------------------------------------------------------
# FTSE MIB — Xtrackers FTSE MIB ETF
# ---------------------------------------------------------------------------
FTSEMIB_ETF_CSV_URL = "https://etf.dws.com/en-it/IE00B53L4X51-xtrackers-ftse-mib-ucits-etf-1c/"


def get_ftsemib(local_only: bool) -> pd.DataFrame:
    r = requests.get(FTSEMIB_ETF_CSV_URL, headers=HEADERS_BROWSER, timeout=30)
    r.raise_for_status()
    content_type = r.headers.get("Content-Type", "")
    if "html" in content_type.lower():
        match = re.search(r'(https?://[^"\']+holdings[^"\']*\.csv)', r.text)
        if not match:
            raise ValueError("Xtrackers serve HTML ma nessun link holdings CSV trovato")
        r2 = requests.get(match.group(1), headers=HEADERS_BROWSER, timeout=30)
        r2.raise_for_status()
        text = r2.content.decode("utf-8", errors="ignore")
    else:
        text = r.content.decode("utf-8", errors="ignore")

    df = pd.read_csv(io.StringIO(text))
    df.columns = [c.strip() for c in df.columns]
    rename_map = {}
    for col in df.columns:
        cl = col.lower()
        if cl in ("ticker", "symbol", "mnemo"):
            rename_map[col] = "ticker"
        elif cl in ("name", "company", "constituent"):
            rename_map[col] = "name"
        elif cl in ("weight", "weight (%)"):
            rename_map[col] = "weight"
    df = df.rename(columns=rename_map)
    if "name" not in df.columns:
        df["name"] = ""
    if "weight" not in df.columns:
        df["weight"] = None
    out = df[["ticker", "name", "weight"]].dropna(subset=["ticker"])
    return _save(out, "ftsemib", "Xtrackers FTSE MIB ETF holdings", local_only)


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
