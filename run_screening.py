"""
Screening automatico giornaliero (lanciato da .github/workflows/run_screening.yml).
I/O su disco; il commit lo fa il workflow. Logica ALLINEATA a watchlist_io:
VWAP rinfrescati sempre (auto+manuali), POC solo su auto, rimozione solo zombie.
CONCETTO POC = ZONA: schema con POC k Low/High; i POC "punto" (manuali/legacy)
ricevono zona derivata ±MANUAL_POC_ZONE_PCT al caricamento (valore POC mai toccato).
"""

import os
import datetime
import pandas as pd
from data_engine import DataEngine, zona_poc_effettiva, MANUAL_POC_ZONE_PCT

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
    "POC 1", "POC 1 Low", "POC 1 High", "Nota POC 1",
    "POC 2", "POC 2 Low", "POC 2 High", "Nota POC 2",
    "POC 3", "POC 3 Low", "POC 3 High", "Nota POC 3",
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
_VWAP_LABELS = {"VWAP 4Y", "VWAP 1Y", "VWAP 3M"}
_COLONNE_NUMERICHE = [
    "Livello 1", "Livello 2", "Livello 3", "VWAP 1", "VWAP 2", "VWAP 3",
    "POC 1", "POC 1 Low", "POC 1 High", "POC 2", "POC 2 Low", "POC 2 High",
    "POC 3", "POC 3 Low", "POC 3 High",
]


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
    for col in _COLONNE_NUMERICHE:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0).astype(float)
    # Migrazione zone: POC punto senza Low/High -> zona derivata (valore POC intatto)
    for k in (1, 2, 3):
        mask = (df[f"POC {k}"] != 0) & ((df[f"POC {k} Low"] == 0) | (df[f"POC {k} High"] == 0))
        if mask.any():
            lo, hi = zip(*[zona_poc_effettiva(p, 0, 0) for p in df.loc[mask, f"POC {k}"]])
            df.loc[mask, f"POC {k} Low"] = lo
            df.loc[mask, f"POC {k} High"] = hi
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
    """Distanza minima prezzo -> zone POC (0 se dentro la zona) e VWAP."""
    dist_poc = 999
    for k in (1, 2, 3):
        poc = _safe_float(row_s.get(f"POC {k}"), 0.0)
        lo, hi = zona_poc_effettiva(poc, row_s.get(f"POC {k} Low"), row_s.get(f"POC {k} High"))
        if poc > 0 and lo > 0 and hi > 0:
            if lo <= prezzo <= hi:
                d = 0.0
            elif prezzo < lo:
                d = abs(prezzo - lo) / lo * 100
            else:
                d = abs(prezzo - hi) / hi * 100
            dist_poc = min(dist_poc, d)
    v4 = _safe_float(row_s.get("VWAP 4Y"), 0.0)
    v1 = _safe_float(row_s.get("VWAP 1Y"), 0.0)
    v3 = _safe_float(row_s.get("VWAP 3M"), 0.0)
    d4 = abs(prezzo - v4) / v4 * 100 if v4 != 0 else 999
    d1 = abs(prezzo - v1) / v1 * 100 if v1 != 0 else 999
    d3 = abs(prezzo - v3) / v3 * 100 if v3 != 0 else 999
    return min(dist_poc, d4, d1, d3)


def _write_vwap(df, idx, row_s):
    pairs = [("VWAP 1", "VWAP 4Y", "VWAP 4Y"),
             ("VWAP 2", "VWAP 1Y", "VWAP 1Y"),
             ("VWAP 3", "VWAP 3M", "VWAP 3M")]
    for col, src, label in pairs:
        df.at[idx, col] = _safe_float(row_s.get(src), 0.0)
        nota_col = "Nota " + col
        existing = str(df.at[idx, nota_col] or "").strip()
        if existing == "" or existing in _VWAP_LABELS:
            df.at[idx, nota_col] = label


def _write_pocs(df, idx, row_s, indice):
    for k in (1, 2, 3):
        df.at[idx, f"POC {k}"] = _safe_float(row_s.get(f"POC {k}"), 0.0)
        df.at[idx, f"POC {k} Low"] = _safe_float(row_s.get(f"POC {k} Low"), 0.0)
        df.at[idx, f"POC {k} High"] = _safe_float(row_s.get(f"POC {k} High"), 0.0)
        df.at[idx, f"Nota POC {k}"] = str(row_s.get(f"Nota POC {k}", "") or "")
    df.at[idx, "Auto_Indice"] = indice


def reconcile(df_wl, df_scr, indice, soglia):
    stats = {"aggiunti": 0, "aggiornati": 0, "vwappati": 0, "in_zona": 0}
    if df_scr.empty:
        return df_wl, stats

    for _, row_s in df_scr.iterrows():
        ticker = str(row_s.get("Ticker", "")).strip().upper()
        if not ticker:
            continue
        prezzo = _safe_float(row_s.get("Prezzo"), 0.0)
        if prezzo == 0:
            continue
        if _dists(row_s, prezzo) <= soglia:
            stats["in_zona"] += 1
        mask = df_wl["Ticker"].str.upper() == ticker
        if mask.any():
            idx = df_wl[mask].index[0]
            origine = str(df_wl.at[idx, "Origine"]).strip().lower()
            _write_vwap(df_wl, idx, row_s)  # sempre
            if origine == "manuale":
                stats["vwappati"] += 1
            else:
                _write_pocs(df_wl, idx, row_s, indice)
                stats["aggiornati"] += 1
        else:
            if _dists(row_s, prezzo) <= soglia:
                nuova = pd.DataFrame([{
                    "Ticker": ticker,
                    "Livello 1": 0, "Nota 1": "", "Livello 2": 0, "Nota 2": "", "Livello 3": 0, "Nota 3": "",
                    "VWAP 1": _safe_float(row_s.get("VWAP 4Y"), 0.0), "Nota VWAP 1": "VWAP 4Y",
                    "VWAP 2": _safe_float(row_s.get("VWAP 1Y"), 0.0), "Nota VWAP 2": "VWAP 1Y",
                    "VWAP 3": _safe_float(row_s.get("VWAP 3M"), 0.0), "Nota VWAP 3": "VWAP 3M",
                    "Screenshot": "", "Origine": "auto",
                    "POC 1": _safe_float(row_s.get("POC 1"), 0.0),
                    "POC 1 Low": _safe_float(row_s.get("POC 1 Low"), 0.0),
                    "POC 1 High": _safe_float(row_s.get("POC 1 High"), 0.0),
                    "Nota POC 1": str(row_s.get("Nota POC 1", "") or ""),
                    "POC 2": _safe_float(row_s.get("POC 2"), 0.0),
                    "POC 2 Low": _safe_float(row_s.get("POC 2 Low"), 0.0),
                    "POC 2 High": _safe_float(row_s.get("POC 2 High"), 0.0),
                    "Nota POC 2": str(row_s.get("Nota POC 2", "") or ""),
                    "POC 3": _safe_float(row_s.get("POC 3"), 0.0),
                    "POC 3 Low": _safe_float(row_s.get("POC 3 Low"), 0.0),
                    "POC 3 High": _safe_float(row_s.get("POC 3 High"), 0.0),
                    "Nota POC 3": str(row_s.get("Nota POC 3", "") or ""),
                    "Auto_Indice": indice,
                }])
                df_wl = pd.concat([df_wl, nuova], ignore_index=True)
                stats["aggiunti"] += 1
    return df_wl, stats


def pulisci_zombie(df_wl, indice, ticker_correnti):
    idx_drop = []
    for idx, row in df_wl.iterrows():
        if str(row.get("Origine", "")).strip().lower() == "auto" and str(row.get("Auto_Indice", "")).strip() == indice:
            if str(row["Ticker"]).strip().upper() not in ticker_correnti:
                idx_drop.append(idx)
    if idx_drop:
        df_wl = df_wl.drop(idx_drop)
    return df_wl, len(idx_drop)


def legacy_cleanup(df_wl, ticker_globali):
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
    tot = {"aggiunti": 0, "aggiornati": 0, "vwappati": 0, "rimossi": 0, "in_zona": 0, "legacy": 0}
    ticker_globali = set()

    # --- Chiamata MULTI-INDICE: UN solo download prezzi per tutti i 5 indici ---
    results_multi = engine.perform_screening_multi(
        INDICI, MIN_MARKET_CAP, SOGLIA_DRAWDOWN, SOGLIA_POC_PCT
    )

    for idx in INDICI:
        result, spost = results_multi.get(idx, ([], []))
        df_scr = pd.DataFrame(result) if result else pd.DataFrame()
        n_trovati = len(df_scr) if not df_scr.empty else 0
        print(f"    [{idx}] titoli in sconto: {n_trovati}")
        ticker_corr = set(str(t).strip().upper() for t in df_scr["Ticker"]) if (not df_scr.empty and "Ticker" in df_scr.columns) else set()
        ticker_globali |= ticker_corr

        df_wl, stats = reconcile(df_wl, df_scr, idx, SOGLIA_PROMO_PCT)
        df_wl, zomb = pulisci_zombie(df_wl, idx, ticker_corr)

        for k in ("aggiunti", "aggiornati", "vwappati", "in_zona"):
            tot[k] += stats.get(k, 0)
        tot["rimossi"] += zomb
        print(f"    [{idx}] reconcile: +{stats['aggiunti']} agg={stats['aggiornati']} vwappati={stats['vwappati']} | in_zona={stats['in_zona']} zombie={zomb}")

    df_wl, leg = legacy_cleanup(df_wl, ticker_globali)
    tot["legacy"] = leg

    save_watchlist_disk(df_wl)
    print("=== Riepilogo automazione watchlist ===")
    print(f"  ➕ aggiunti 🤖      : {tot['aggiunti']}")
    print(f"  🔄 aggiornati (auto): {tot['aggiornati']}")
    print(f"  🔃 VWAP rinfrescati : {tot['vwappati']}  (su manuali; VWAP auto già contati in aggiornati)")
    print(f"  🗑️ rimossi (usciti) : {tot['rimossi']}  (+ legacy normalizzati: {tot['legacy']})")
    print(f"  🎯 in zona tot      : {tot['in_zona']}")
    print("=== Fine. Il workflow committerà argo_database.json + watchlist.csv ===")


if __name__ == "__main__":
    main()
