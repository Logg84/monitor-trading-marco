"""
Screening automatico giornaliero (lanciato da .github/workflows/run_screening.yml).
I/O su disco; il commit lo fa il workflow. Logica di riconciliazione ALLINEATA a watchlist_io.
"""

import os
import datetime
import pandas as pd
from data_engine import DataEngine

CSV_PATH = "watchlist.csv"

MIN_MARKET_CAP = 2.5e9
SOGLIA_DRAWDOWN = 25.0
SOGLIA_POC_PCT = 2.0
SOGLIA_PROMO_PCT = 2.5

INDICI = ["S&P 500", "NASDAQ 100", "DAX (Germania)", "CAC 40 (Francia)", "FTSE MIB (Italia)"]

COLONNE_ATTESE = [
    "Ticker",
    "Livello 1", "Nota 1", "Livello 2", "Nota 2", "Livello 3", "Nota 3",
    "VWAP 1", "Nota VWAP 1", "VWAP 2", "Nota VWAP 2", "VWAP 3", "Nota VWAP 3",
    "Screenshot", "Origine",
    "POC 1", "Nota POC 1", "POC 2", "Nota POC 2", "POC 3", "Nota POC 3",
    "Auto_Indice",
]
ALIAS_COLONNE = {
    "ticker": "Ticker", "livello": "Livello 1",
    "livello_1": "Livello 1", "livello_2": "Livello 2", "livello_3": "Livello 3",
    "vwap_1": "VWAP 1", "vwap_2": "VWAP 2", "vwap_3": "VWAP 3",
    "origine": "Origine",
    "POC": "POC 1", "poc": "POC 1",
    "Nota POC": "Nota POC 1", "nota poc": "Nota POC 1",
    "auto_indice": "Auto_Indice",
}
_TEXT_COLS = {"Screenshot", "Origine", "Auto_Indice"}


def _is_text_col(col: str) -> bool:
    return col.startswith("Nota") or col in _TEXT_COLS


def load_watchlist_disk() -> pd.DataFrame:
    if not os.path.exists(CSV_PATH):
        return pd.DataFrame(columns=COLONNE_ATTESE)
    df = pd.read_csv(CSV_PATH)
    df = df.rename(columns=ALIAS_COLONNE)
    for col in COLONNE_ATTESE:
        if col not in df.columns:
            df[col] = "" if _is_text_col(col) else 0
    df = df[COLONNE_ATTESE]
    if "Origine" in df.columns:
        df["Origine"] = df["Origine"].fillna("manuale").replace("", "manuale")
    for col in COLONNE_ATTESE:
        if _is_text_col(col):
            df[col] = df[col].fillna("").astype(str).replace("nan", "")
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated()]
    return df


def save_watchlist_disk(df: pd.DataFrame):
    df.to_csv(CSV_PATH, index=False)


def _safe_float(val, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        f = float(val)
        return default if pd.isna(f) else f
    except (ValueError, TypeError):
        return default


def _dists(row_s, prezzo):
    poc_vals = [_safe_float(row_s.get(f"POC {k}"), 0.0) for k in (1, 2, 3)]
    poc_vals = [v for v in poc_vals if v != 0]
    dist_poc = min(abs(prezzo - v) / v * 100 for v in poc_vals) if poc_vals else 999
    v4 = _safe_float(row_s.get("VWAP 4Y"), 0.0)
    v1 = _safe_float(row_s.get("VWAP 1Y"), 0.0)
    v3 = _safe_float(row_s.get("VWAP 3M"), 0.0)
    d4 = abs(prezzo - v4) / v4 * 100 if v4 != 0 else 999
    d1 = abs(prezzo - v1) / v1 * 100 if v1 != 0 else 999
    d3 = abs(prezzo - v3) / v3 * 100 if v3 != 0 else 999
    return min(dist_poc, d4, d1, d3)


def _write_pocs(df, idx, row_s, indice):
    for k in (1, 2, 3):
        df.at[idx, f"POC {k}"] = _safe_float(row_s.get(f"POC {k}"), 0.0)
        df.at[idx, f"Nota POC {k}"] = str(row_s.get(f"Nota POC {k}", "") or "")
    df.at[idx, "Auto_Indice"] = indice


def reconcile(df_wl, df_scr, indice, soglia):
    stats = {"aggiunti": 0, "aggiornati": 0, "rimossi": 0, "in_zona": 0, "saltati": 0, "saltati_tickers": []}
    if df_scr.empty:
        return df_wl, stats

    for _, row_s in df_scr.iterrows():
        ticker = str(row_s.get("Ticker", "")).strip().upper()
        if not ticker:
            continue
        prezzo = _safe_float(row_s.get("Prezzo"), 0.0)
        if prezzo == 0:
            continue
        if _dists(row_s, prezzo) > soglia:
            continue
        stats["in_zona"] += 1
        mask = df_wl["Ticker"].str.upper() == ticker
        if mask.any():
            idx = df_wl[mask].index[0]
            origine = str(df_wl.at[idx, "Origine"]).strip().lower()
            if origine == "manuale":
                stats["saltati"] += 1
                stats["saltati_tickers"].append(ticker)
                continue
            _write_pocs(df_wl, idx, row_s, indice)
            df_wl.at[idx, "VWAP 1"] = _safe_float(row_s.get("VWAP 4Y"), 0.0); df_wl.at[idx, "Nota VWAP 1"] = "VWAP 4Y"
            df_wl.at[idx, "VWAP 2"] = _safe_float(row_s.get("VWAP 1Y"), 0.0); df_wl.at[idx, "Nota VWAP 2"] = "VWAP 1Y"
            df_wl.at[idx, "VWAP 3"] = _safe_float(row_s.get("VWAP 3M"), 0.0); df_wl.at[idx, "Nota VWAP 3"] = "VWAP 3M"
            stats["aggiornati"] += 1
        else:
            nuova = pd.DataFrame([{
                "Ticker": ticker,
                "Livello 1": 0, "Nota 1": "", "Livello 2": 0, "Nota 2": "", "Livello 3": 0, "Nota 3": "",
                "VWAP 1": _safe_float(row_s.get("VWAP 4Y"), 0.0), "Nota VWAP 1": "VWAP 4Y",
                "VWAP 2": _safe_float(row_s.get("VWAP 1Y"), 0.0), "Nota VWAP 2": "VWAP 1Y",
                "VWAP 3": _safe_float(row_s.get("VWAP 3M"), 0.0), "Nota VWAP 3": "VWAP 3M",
                "Screenshot": "", "Origine": "auto",
                "POC 1": _safe_float(row_s.get("POC 1"), 0.0), "Nota POC 1": str(row_s.get("Nota POC 1", "") or ""),
                "POC 2": _safe_float(row_s.get("POC 2"), 0.0), "Nota POC 2": str(row_s.get("Nota POC 2", "") or ""),
                "POC 3": _safe_float(row_s.get("POC 3"), 0.0), "Nota POC 3": str(row_s.get("Nota POC 3", "") or ""),
                "Auto_Indice": indice,
            }])
            df_wl = pd.concat([df_wl, nuova], ignore_index=True)
            stats["aggiunti"] += 1

    da_rimuovere = set()
    for _, row_s in df_scr.iterrows():
        ticker = str(row_s.get("Ticker", "")).strip().upper()
        if not ticker:
            continue
        prezzo = _safe_float(row_s.get("Prezzo"), 0.0)
        if prezzo == 0:
            continue
        if _dists(row_s, prezzo) > soglia:
            da_rimuovere.add(ticker)
    for ticker in da_rimuovere:
        mask = df_wl["Ticker"].str.upper() == ticker
        if mask.any():
            idx = df_wl[mask].index[0]
            if str(df_wl.at[idx, "Origine"]).strip().lower() == "auto":
                df_wl = df_wl.drop(idx)
                stats["rimossi"] += 1
    return df_wl, stats


def pulisci_zombie(df_wl, indice, ticker_correnti):
    """Rimuove gli auto il cui Auto_Indice == indice e che non sono più nello screening di quell'indice."""
    idx_drop = []
    for idx, row in df_wl.iterrows():
        if str(row.get("Origine", "")).strip().lower() == "auto" and str(row.get("Auto_Indice", "")).strip() == indice:
            if str(row["Ticker"]).strip().upper() not in ticker_correnti:
                idx_drop.append(idx)
    if idx_drop:
        df_wl = df_wl.drop(idx_drop)
    return df_wl, len(idx_drop)


def legacy_cleanup(df_wl, ticker_globali):
    """Rimuove gli auto 'legacy' (Auto_Indice vuoto, pre-migrazione) usciti dal metodo ovunque."""
    idx_drop = []
    for idx, row in df_wl.iterrows():
        if str(row.get("Origine", "")).strip().lower() == "auto" and str(row.get("Auto_Indice", "")).strip() == "":
            if str(row["Ticker"]).strip().upper() not in ticker_globali:
                idx_drop.append(idx)
    if idx_drop:
        df_wl = df_wl.drop(idx_drop)
    return df_wl, len(idx_drop)


def main():
    print(f"=== Screening automatico {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} ===")
    engine = DataEngine(base_dir=".")

    df_wl = load_watchlist_disk()
    tot = {"aggiunti": 0, "aggiornati": 0, "rimossi": 0, "in_zona": 0, "saltati": 0, "zombie": 0, "legacy": 0}
    ticker_globali = set()

    for idx in INDICI:
        print(f"--- Screening: {idx} ---")
        try:
            result, spost = engine.perform_screening(idx, MIN_MARKET_CAP, SOGLIA_DRAWDOWN, SOGLIA_POC_PCT)
        except Exception as e:
            print(f"ERRORE screening {idx}: {e}")
            continue
        df_scr = pd.DataFrame(result) if result else pd.DataFrame()
        n_trovati = len(df_scr) if not df_scr.empty else 0
        print(f"    titoli in sconto: {n_trovati}")
        ticker_corr = set(str(t).strip().upper() for t in df_scr["Ticker"]) if (not df_scr.empty and "Ticker" in df_scr.columns) else set()
        ticker_globali |= ticker_corr

        df_wl, stats = reconcile(df_wl, df_scr, idx, SOGLIA_PROMO_PCT)
        df_wl, zomb = pulisci_zombie(df_wl, idx, ticker_corr)

        for k in ("aggiunti", "aggiornati", "rimossi", "in_zona", "saltati"):
            tot[k] += stats.get(k, 0)
        tot["zombie"] += zomb
        print(f"    reconcile: +{stats['aggiunti']} agg={stats['aggiornati']} -{stats['rimossi']} | in_zona={stats['in_zona']} saltati(manuali)={stats['saltati']} zombie={zomb}")

    df_wl, leg = legacy_cleanup(df_wl, ticker_globali)
    tot["legacy"] = leg

    save_watchlist_disk(df_wl)
    print("=== Riepilogo automazione watchlist ===")
    print(f"  ➕ aggiunti 🤖 : {tot['aggiunti']}")
    print(f"  🔄 aggiornati  : {tot['aggiornati']}")
    print(f"  🧹 fuori zona  : {tot['rimossi']}")
    print(f"  🗑️ zombie      : {tot['zombie']}  (+ legacy normalizzati rimossi: {tot['legacy']})")
    print(f"  🎯 in zona tot : {tot['in_zona']}  (di cui 🔒 manuali intatti: {tot['saltati']})")
    print("=== Fine. Il workflow committerà argo_database.json + watchlist.csv ===")


if __name__ == "__main__":
    main()
