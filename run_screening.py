"""
Screening automatico giornaliero (lanciato da .github/workflows/run_screening.yml).

Fa tre cose, in ordine:
 1. Esegue perform_screening sui 5 indici (motore daily in data_engine.py),
    che salva da solo argo_database.json / screener_state.json / fundamentals_cache.json.
 2. Riconcilia la watchlist (modello a due origini): promuove in 'auto' i titoli che
    toccano POC/VWAP entro la soglia, aggiorna gli auto esistenti, rimuove gli auto
    usciti dalla zona o usciti dallo screening. I 'manuale' non vengono MAI toccati.
 3. Riscrive watchlist.csv su disco; il workflow poi fa il commit su GitHub.

NOTA ARCHITETTURA: la logica di riconciliazione qui sotto è una COPIA di quella in
watchlist_io.promuovi_auto_da_screener / pulisci_auto_zombie, adattata a I/O su disco
(invece che API GitHub) perché questo script gira in GitHub Actions, NON in Streamlit.
Se modifichi le soglie o le regole, ALLINEA i due file (cerca "ALLINEARE CON watchlist_io").
"""

import os
import datetime
import pandas as pd
from data_engine import DataEngine

CSV_PATH = "watchlist.csv"

# --- Parametri screening (coerenti con i default della pagina) ---
MIN_MARKET_CAP = 2.5e9
SOGLIA_DRAWDOWN = 25.0
SOGLIA_POC_PCT = 2.0
SOGLIA_PROMO_PCT = 2.5   # entro questa % da POC/VWAP -> promozione auto

INDICI = ["S&P 500", "NASDAQ 100", "DAX (Germania)", "CAC 40 (Francia)", "FTSE MIB (Italia)"]

# Schema watchlist (ALLINEARE CON watchlist_io.COLONNE_ATTESE)
COLONNE_ATTESE = [
    "Ticker",
    "Livello 1", "Nota 1", "Livello 2", "Nota 2", "Livello 3", "Nota 3",
    "VWAP 1", "Nota VWAP 1", "VWAP 2", "Nota VWAP 2", "VWAP 3", "Nota VWAP 3",
    "Screenshot", "Origine", "POC", "Nota POC",
]
ALIAS_COLONNE = {
    "ticker": "Ticker", "livello": "Livello 1",
    "livello_1": "Livello 1", "livello_2": "Livello 2", "livello_3": "Livello 3",
    "vwap_1": "VWAP 1", "vwap_2": "VWAP 2", "vwap_3": "VWAP 3",
    "origine": "Origine", "poc": "POC",
}


# ---------------------------------------------------------------
# I/O watchlist SU DISCO (il commit lo fa il workflow, non questo script)
# ---------------------------------------------------------------
def load_watchlist_disk() -> pd.DataFrame:
    if not os.path.exists(CSV_PATH):
        return pd.DataFrame(columns=COLONNE_ATTESE)
    df = pd.read_csv(CSV_PATH)
    df = df.rename(columns=ALIAS_COLONNE)
    for col in COLONNE_ATTESE:
        if col not in df.columns:
            df[col] = "" if (col.startswith("Nota") or col in ("Screenshot", "Origine")) else 0
    df = df[COLONNE_ATTESE]
    if "Origine" in df.columns:
        df["Origine"] = df["Origine"].fillna("manuale").replace("", "manuale")
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated()]
    return df


def save_watchlist_disk(df: pd.DataFrame):
    df.to_csv(CSV_PATH, index=False)


# ---------------------------------------------------------------
# Helper (ALLINEARE CON watchlist_io)
# ---------------------------------------------------------------
def parse_poc_string(poc_str: str) -> float:
    if not poc_str or poc_str == "N/D":
        return 0.0
    try:
        return float(poc_str.split(" ")[0])
    except Exception:
        return 0.0


def _safe_float(val, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        f = float(val)
        return default if pd.isna(f) else f
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------
# RICONCILIAZIONE (ALLINEARE CON watchlist_io.promuovi_auto_da_screener)
# ---------------------------------------------------------------
def reconcile(df_wl: pd.DataFrame, df_scr: pd.DataFrame, indice: str, soglia: float):
    """Promozione auto + auto-pulizia 'fuori zona'. Opera in memoria su df_wl.
    Ritorna (df_wl, stats). Non tocca mai i manuali."""
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
        poc_val = parse_poc_string(str(row_s.get("POC più vicino", "N/D")))
        dist_poc = abs(prezzo - poc_val) / poc_val * 100 if poc_val != 0 else 999
        vwap_4y = _safe_float(row_s.get("VWAP 4Y"), 0.0)
        vwap_1y = _safe_float(row_s.get("VWAP 1Y"), 0.0)
        vwap_3m = _safe_float(row_s.get("VWAP 3M"), 0.0)
        dist_vwap_4y = abs(prezzo - vwap_4y) / vwap_4y * 100 if vwap_4y != 0 else 999
        dist_vwap_1y = abs(prezzo - vwap_1y) / vwap_1y * 100 if vwap_1y != 0 else 999
        dist_vwap_3m = abs(prezzo - vwap_3m) / vwap_3m * 100 if vwap_3m != 0 else 999
        if min(dist_poc, dist_vwap_4y, dist_vwap_1y, dist_vwap_3m) > soglia:
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
            df_wl.at[idx, "POC"] = poc_val
            df_wl.at[idx, "Nota POC"] = f"POC da Screener ({indice})"
            df_wl.at[idx, "VWAP 1"] = vwap_4y; df_wl.at[idx, "Nota VWAP 1"] = "VWAP 4Y"
            df_wl.at[idx, "VWAP 2"] = vwap_1y; df_wl.at[idx, "Nota VWAP 2"] = "VWAP 1Y"
            df_wl.at[idx, "VWAP 3"] = vwap_3m; df_wl.at[idx, "Nota VWAP 3"] = "VWAP 3M"
            stats["aggiornati"] += 1
        else:
            nuova = pd.DataFrame([{
                "Ticker": ticker,
                "Livello 1": 0, "Nota 1": "", "Livello 2": 0, "Nota 2": "", "Livello 3": 0, "Nota 3": "",
                "VWAP 1": vwap_4y, "Nota VWAP 1": "VWAP 4Y",
                "VWAP 2": vwap_1y, "Nota VWAP 2": "VWAP 1Y",
                "VWAP 3": vwap_3m, "Nota VWAP 3": "VWAP 3M",
                "Screenshot": "", "Origine": "auto", "POC": poc_val,
                "Nota POC": f"POC da Screener ({indice})",
            }])
            df_wl = pd.concat([df_wl, nuova], ignore_index=True)
            stats["aggiunti"] += 1

    # Auto-pulizia 'fuori zona' (solo auto)
    da_rimuovere = set()
    for _, row_s in df_scr.iterrows():
        ticker = str(row_s.get("Ticker", "")).strip().upper()
        if not ticker:
            continue
        prezzo = _safe_float(row_s.get("Prezzo"), 0.0)
        if prezzo == 0:
            continue
        poc_val = parse_poc_string(str(row_s.get("POC più vicino", "N/D")))
        dist_poc = abs(prezzo - poc_val) / poc_val * 100 if poc_val != 0 else 999
        vwap_4y = _safe_float(row_s.get("VWAP 4Y"), 0.0)
        vwap_1y = _safe_float(row_s.get("VWAP 1Y"), 0.0)
        vwap_3m = _safe_float(row_s.get("VWAP 3M"), 0.0)
        dist_vwap_4y = abs(prezzo - vwap_4y) / vwap_4y * 100 if vwap_4y != 0 else 999
        dist_vwap_1y = abs(prezzo - vwap_1y) / vwap_1y * 100 if vwap_1y != 0 else 999
        dist_vwap_3m = abs(prezzo - vwap_3m) / vwap_3m * 100 if vwap_3m != 0 else 999
        if min(dist_poc, dist_vwap_4y, dist_vwap_1y, dist_vwap_3m) > soglia:
            da_rimuovere.add(ticker)
    for ticker in da_rimuovere:
        mask = df_wl["Ticker"].str.upper() == ticker
        if mask.any():
            idx = df_wl[mask].index[0]
            if str(df_wl.at[idx, "Origine"]).strip().lower() == "auto":
                df_wl = df_wl.drop(idx)
                stats["rimossi"] += 1
    return df_wl, stats


# ---------------------------------------------------------------
# PULIZIA ZOMBIE (ALLINEARE CON pages/2_Screening.pulisci_auto_zombie)
# ---------------------------------------------------------------
def pulisci_zombie(df_wl: pd.DataFrame, indice: str, ticker_correnti: set):
    """Rimuove gli auto 'di proprietà' di `indice` usciti dallo screening."""
    tag = f"({indice})"
    idx_drop = []
    for idx, row in df_wl.iterrows():
        if str(row.get("Origine", "")).strip().lower() == "auto" and tag in str(row.get("Nota POC", "")):
            if str(row["Ticker"]).strip().upper() not in ticker_correnti:
                idx_drop.append(idx)
    if idx_drop:
        df_wl = df_wl.drop(idx_drop)
    return df_wl, len(idx_drop)


# ---------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------
def main():
    print(f"=== Screening automatico {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} ===")
    engine = DataEngine(base_dir=".")  # legge/scrive i json nella root del repo

    df_wl = load_watchlist_disk()
    tot = {"aggiunti": 0, "aggiornati": 0, "rimossi": 0, "in_zona": 0, "saltati": 0, "zombie": 0}

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

        df_wl, stats = reconcile(df_wl, df_scr, idx, SOGLIA_PROMO_PCT)
        ticker_corr = set(str(t).strip().upper() for t in df_scr["Ticker"]) if (not df_scr.empty and "Ticker" in df_scr.columns) else set()
        df_wl, zomb = pulisci_zombie(df_wl, idx, ticker_corr)

        for k in ("aggiunti", "aggiornati", "rimossi", "in_zona", "saltati"):
            tot[k] += stats.get(k, 0)
        tot["zombie"] += zomb
        print(f"    reconcile: +{stats['aggiunti']} agg={stats['aggiornati']} -{stats['rimossi']} | in_zona={stats['in_zona']} saltati(manuali)={stats['saltati']} zombie={zomb}")

    save_watchlist_disk(df_wl)
    print("=== Riepilogo automazione watchlist ===")
    print(f"  ➕ aggiunti 🤖 : {tot['aggiunti']}")
    print(f"  🔄 aggiornati  : {tot['aggiornati']}")
    print(f"  🧹 fuori zona  : {tot['rimossi']}")
    print(f"  🗑️ zombie      : {tot['zombie']}")
    print(f"  🎯 in zona tot : {tot['in_zona']}  (di cui 🔒 manuali intatti: {tot['saltati']})")
    print("=== Fine. Il workflow committerà argo_database.json + watchlist.csv ===")


if __name__ == "__main__":
    main()
