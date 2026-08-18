"""
CFTC COT parser: reads annual (Excel zip) and weekly (comma-delimited txt).
Builds historical data, computes contrarian scores for Money Manager and
Producers, applies the "producer extreme" rule.
"""
from __future__ import annotations

import zipfile
from io import BytesIO, StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
COT_DIR = DATA_DIR / "cot"

TARGET_INDEX = ["E-MINI S&P", "S&P 500", "NASDAQ"]
TARGET_COMMODITY = ["GOLD", "SILVER", "CRUDE OIL", "NATURAL GAS",
                    "COPPER", "CORN", "WHEAT", "SOYBEANS"]

MM_KEYS = ["managed money", "money manager", "non-commercial", "leveraged funds"]
PROD_KEYS = ["producer", "commercial", "dealer"]

DATE_COLS = ["report date", "week", "date", "as of date"]

def _find_col(cols, *keys) -> str | None:
    for c in cols:
        if all(k.lower() in c.lower() for k in keys):
            return c
    return None

def _with_meta(df: pd.DataFrame, source: str, fname: str) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None
    if "Market and Exchange Names" not in df.columns:
        return None
    df = df.copy()
    df["_source"] = source
    df["_file"] = fname
    return df

def _read_excel_bytes(data: bytes, source: str, fname: str) -> list[pd.DataFrame]:
    engine = "xlrd" if fname.lower().endswith(".xls") else "openpyxl"
    out = []
    try:
        sheets = pd.read_excel(BytesIO(data), sheet_name=None, engine=engine)
        for _, df in sheets.items():
            f = _with_meta(df, source, fname)
            if f is not None:
                out.append(f)
    except Exception:
        pass
    return out

def _read_text_bytes(data: bytes, source: str, fname: str) -> list[pd.DataFrame]:
    try:
        text = data.decode("utf-8", errors="ignore")
        df = pd.read_csv(StringIO(text), skipinitialspace=True)
        f = _with_meta(df, source, fname)
        return [f] if f is not None else []
    except Exception:
        return []

def _frames_from_file(path: Path) -> list[pd.DataFrame]:
    low = path.name.lower()
    if low.endswith(".zip"):
        frames = []
        try:
            with zipfile.ZipFile(path) as zf:
                for name in zf.namelist():
                    nlow = name.lower()
                    with zf.open(name) as f:
                        data = f.read()
                    if nlow.endswith((".xls", ".xlsx")):
                        frames.extend(_read_excel_bytes(data, path.stem, name))
                    elif nlow.endswith((".txt", ".csv")):
                        frames.extend(_read_text_bytes(data, path.stem, name))
        except Exception:
            pass
        return frames
    if low.endswith((".xls", ".xlsx")):
        return _read_excel_bytes(path.read_bytes(), path.stem, path.name)
    if low.endswith((".txt", ".csv")):
        return _read_text_bytes(path.read_bytes(), path.stem, path.name)
    return []

def _load_all() -> pd.DataFrame | None:
    COT_DIR.mkdir(parents=True, exist_ok=True)
    frames = []
    for p in sorted(COT_DIR.glob("*")):
        frames.extend(_frames_from_file(p))
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)

def _sort_series(sub: pd.DataFrame) -> pd.DataFrame:
    date_col = _find_col(sub.columns, *DATE_COLS)
    if date_col:
        sub = sub.copy()
        sub["_date"] = pd.to_datetime(sub[date_col], errors="coerce")
        return sub.sort_values(["_date", "_source", "_file"]).reset_index(drop=True)
    return sub.sort_values(["_source", "_file"]).reset_index(drop=True)

def _net_series(sub: pd.DataFrame, keys: list[str]) -> pd.Series | None:
    long_col = short_col = None
    for k in keys:
        long_col = _find_col(sub.columns, k, "long")
        short_col = _find_col(sub.columns, k, "short")
        if long_col and short_col:
            break
    if not long_col or not short_col:
        return None
    lng = pd.to_numeric(sub[long_col], errors="coerce")
    sh = pd.to_numeric(sub[short_col], errors="coerce")
    net = (lng - sh).dropna()
    return net if len(net) >= 5 else None

def _pct_score(net: pd.Series, invert: bool) -> tuple[float, float, float]:
    cur = float(net.iloc[-1])
    pct = float((net < cur).mean() * 100)
    sign = -1.0 if invert else 1.0
    return float(np.clip(sign * (pct - 50) * 2, -100, 100)), pct, cur

def compute_cot_scores() -> dict | None:
    df = _load_all()
    if df is None:
        return None

    mm_scores, pr_scores, mm_det, pr_det = [], [], [], []
    extreme = False
    markets_used = []

    for market in TARGET_INDEX + TARGET_COMMODITY:
        mask = df["Market and Exchange Names"].str.contains(market, case=False, na=False)
        sub = df[mask]
        if sub.empty:
            continue
        sub = _sort_series(sub)

        mm_net = _net_series(sub, MM_KEYS)
        pr_net = _net_series(sub, PROD_KEYS)
        if mm_net is None and pr_net is None:
            continue
        markets_used.append(market)

        if mm_net is not None:
            s, pct, cur = _pct_score(mm_net, invert=True)
            mm_scores.append(s)
            mm_det.append(f"{market} {pct:.0f}%")
        if pr_net is not None:
            s, pct, cur = _pct_score(pr_net, invert=False)
            pr_scores.append(s)
            pr_det.append(f"{market} {pct:.0f}%")
            if market in TARGET_COMMODITY and (pct <= 10 or pct >= 90):
                extreme = True

    if not markets_used:
        return None

    return {
        "market": ", ".join(markets_used),
        "n_obs": int(len(df)),
        "managed_money": float(np.mean(mm_scores)) if mm_scores else 0.0,
        "producers": float(np.mean(pr_scores)) if pr_scores else 0.0,
        "managed_money_detail": "percentiles: " + ", ".join(mm_det) if mm_det else "",
        "producers_detail": "percentiles: " + ", ".join(pr_det) if pr_det else "",
        "extreme_producer": extreme,
    }

@st.cache_data(ttl=7 * 86400, show_spinner=False)
def get_cot_scores() -> dict | None:
    return compute_cot_scores()

def list_files() -> list[Path]:
    COT_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(COT_DIR.glob("*"), reverse=True)