"""
Modulo condiviso per la gestione della watchlist su GitHub.
Usato da app.py (portale alert) e pages/2_Screening.py (promozione auto).

Contiene:
- Lettura/scrittura watchlist.csv su GitHub (via API, base64).
- Logica di promozione auto dallo screener (modello a due origini: manuale/auto).
- Auto-pulizia dei titoli auto che non rispettano più la soglia di promozione.
"""

import os
import base64
import requests
import pandas as pd
import streamlit as st

# ---------------------------------------------------------------
# SCHEMA WATCHLIST (allineato a app.py + Origine + POC + Nota POC)
# ---------------------------------------------------------------
COLONNE_ATTESE = [
    "Ticker",
    "Livello 1", "Nota 1", "Livello 2", "Nota 2", "Livello 3", "Nota 3",
    "VWAP 1", "Nota VWAP 1", "VWAP 2", "Nota VWAP 2", "VWAP 3", "Nota VWAP 3",
    "Screenshot",
    "Origine",       # manuale | auto (default manuale per proteggere i titoli esistenti)
    "POC",           # POC operativo portato dallo screener (colonna separata dai livelli manuali)
    "Nota POC",
]

ALIAS_COLONNE = {
    "ticker": "Ticker",
    "livello": "Livello 1",
    "livello_1": "Livello 1", "livello_2": "Livello 2", "livello_3": "Livello 3",
    "vwap_1": "VWAP 1", "vwap_2": "VWAP 2", "vwap_3": "VWAP 3",
    "origine": "Origine",
    "poc": "POC",
}

CSV_PATH = "watchlist.csv"

# Secrets GitHub (configurati in Streamlit Cloud secrets)
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN") if hasattr(st, "secrets") else os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = st.secrets.get("GITHUB_REPO") if hasattr(st, "secrets") else os.environ.get("GITHUB_REPO")


# ---------------------------------------------------------------
# LETTURA / SCRITTURA WATCHLIST SU GITHUB
# ---------------------------------------------------------------
def carica_watchlist_da_github() -> pd.DataFrame:
    """Legge watchlist.csv da GitHub (via API, base64 decode).
    Ritorna un DataFrame con COLONNE_ATTESE, default Origine=manuale."""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return pd.DataFrame(columns=COLONNE_ATTESE)

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{CSV_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    try:
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            return pd.DataFrame(columns=COLONNE_ATTESE)
        contenuto = base64.b64decode(r.json()["content"]).decode()
        df = pd.read_csv(pd.io.common.StringIO(contenuto))
    except Exception as e:
        print(f"Errore lettura watchlist da GitHub: {e}")
        return pd.DataFrame(columns=COLONNE_ATTESE)

    df = df.rename(columns=ALIAS_COLONNE)

    for col in COLONNE_ATTESE:
        if col not in df.columns:
            df[col] = "" if (col.startswith("Nota") or col in ("Screenshot", "Origine")) else 0

    df = df[COLONNE_ATTESE]

    # Default Origine = manuale per le righe esistenti (protegge i titoli manuali)
    if "Origine" in df.columns:
        df["Origine"] = df["Origine"].fillna("manuale").replace("", "manuale")

    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated()]

    return df


def commit_csv_su_github(df: pd.DataFrame):
    """Scrive watchlist.csv su GitHub (GET sha, PUT content base64)."""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        print("GITHUB_TOKEN o GITHUB_REPO non configurati, skip commit.")
        return

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{CSV_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    r = requests.get(url, headers=headers)
    sha = r.json().get("sha") if r.status_code == 200 else None

    contenuto_b64 = base64.b64encode(df.to_csv(index=False).encode()).decode()
    payload = {
        "message": "Aggiorna watchlist.csv (promozione auto + auto-pulizia)",
        "content": contenuto_b64,
        "branch": "main",
    }
    if sha:
        payload["sha"] = sha

    resp = requests.put(url, headers=headers, json=payload)
    if resp.status_code not in (200, 201):
        print(f"Commit watchlist su GitHub fallito: {resp.status_code} {resp.text[:200]}")


# ---------------------------------------------------------------
# PARSING POC (da stringa "199.17 (2022)" a float 199.17)
# ---------------------------------------------------------------
def parse_poc_string(poc_str: str) -> float:
    """Estrae il valore numerico del POC dalla stringa '199.17 (2022)'. Ritorna 0 se 'N/D' o invalido."""
    if not poc_str or poc_str == "N/D":
        return 0.0
    try:
        return float(poc_str.split(" ")[0])
    except Exception:
        return 0.0


def _safe_float(val, default: float = 0.0) -> float:
    """Converte a float in modo sicuro: None/''/NaN/'N/D' -> default."""
    if val is None:
        return default
    try:
        f = float(val)
        return default if pd.isna(f) else f
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------
# PROMOZIONE AUTO + AUTO-PULIZIA
# ---------------------------------------------------------------
def promuovi_auto_da_screener(
    df_screener: pd.DataFrame,
    indice_corrente: str,
    df_screener_precedente: pd.DataFrame = None,
    soglia_trigger_pct: float = 2.5,
) -> dict:
    """
    Promuove i titoli dello screener nella watchlist (Origine=auto) se il prezzo
    è entro ±soglia_trigger_pct da POC o VWAP 3M/1Y/4Y.
    Auto-pulizia: rimuove i titoli auto che non rispettano più la soglia.
    Non tocca mai i titoli manuali (Origine=manuale).
    """
    if df_screener.empty:
        return {"aggiunti": 0, "rimossi": 0, "aggiornati": 0}

    df_watchlist = carica_watchlist_da_github()
    aggiunti, rimossi, aggiornati = 0, 0, 0

    # ---------------------------------------------------------------
    # 1. PROMOZIONE AUTO: aggiungi/aggiorna i titoli promovibili
    # ---------------------------------------------------------------
    for _, row_s in df_screener.iterrows():
        ticker = str(row_s.get("Ticker", "")).strip().upper()
        if not ticker:
            continue

        prezzo = _safe_float(row_s.get("Prezzo"), 0.0)
        if prezzo == 0:
            continue

        # Distanze % da POC e VWAP. NON leggo "Distanza POC (%)" (può essere "N/D"):
        # ricalcolo la distanza dal valore numerico del POC, come per i VWAP.
        poc_val = parse_poc_string(str(row_s.get("POC più vicino", "N/D")))
        dist_poc = abs(prezzo - poc_val) / poc_val * 100 if poc_val != 0 else 999

        vwap_4y = _safe_float(row_s.get("VWAP 4Y"), 0.0)
        vwap_1y = _safe_float(row_s.get("VWAP 1Y"), 0.0)
        vwap_3m = _safe_float(row_s.get("VWAP 3M"), 0.0)

        dist_vwap_4y = abs(prezzo - vwap_4y) / vwap_4y * 100 if vwap_4y != 0 else 999
        dist_vwap_1y = abs(prezzo - vwap_1y) / vwap_1y * 100 if vwap_1y != 0 else 999
        dist_vwap_3m = abs(prezzo - vwap_3m) / vwap_3m * 100 if vwap_3m != 0 else 999

        # Il titolo è promovibile se il prezzo è entro ±soglia da almeno un livello
        min_dist = min(dist_poc, dist_vwap_4y, dist_vwap_1y, dist_vwap_3m)
        if min_dist > soglia_trigger_pct:
            continue  # Non promovibile

        # Verifico se il ticker esiste già nella watchlist
        if ticker in df_watchlist["Ticker"].str.upper().values:
            idx = df_watchlist[df_watchlist["Ticker"].str.upper() == ticker].index[0]
            origine = str(df_watchlist.at[idx, "Origine"]).strip().lower()

            if origine == "manuale":
                continue  # Titolo manuale: sacro, non lo tocco

            # Titolo auto: aggiorno i numeri (POC, VWAP)
            df_watchlist.at[idx, "POC"] = poc_val
            df_watchlist.at[idx, "Nota POC"] = f"POC da Screener ({indice_corrente})"
            df_watchlist.at[idx, "VWAP 1"] = vwap_4y
            df_watchlist.at[idx, "Nota VWAP 1"] = "VWAP 4Y"
            df_watchlist.at[idx, "VWAP 2"] = vwap_1y
            df_watchlist.at[idx, "Nota VWAP 2"] = "VWAP 1Y"
            df_watchlist.at[idx, "VWAP 3"] = vwap_3m
            df_watchlist.at[idx, "Nota VWAP 3"] = "VWAP 3M"
            aggiornati += 1
        else:
            # Titolo nuovo: lo aggiungo con Origine=auto
            nuova_riga = pd.DataFrame([{
                "Ticker": ticker,
                "Livello 1": 0, "Nota 1": "",
                "Livello 2": 0, "Nota 2": "",
                "Livello 3": 0, "Nota 3": "",
                "VWAP 1": vwap_4y, "Nota VWAP 1": "VWAP 4Y",
                "VWAP 2": vwap_1y, "Nota VWAP 2": "VWAP 1Y",
                "VWAP 3": vwap_3m, "Nota VWAP 3": "VWAP 3M",
                "Screenshot": "",
                "Origine": "auto",
                "POC": poc_val,
                "Nota POC": f"POC da Screener ({indice_corrente})",
            }])
            df_watchlist = pd.concat([df_watchlist, nuova_riga], ignore_index=True)
            aggiunti += 1

    # ---------------------------------------------------------------
    # 2. AUTO-PULIZIA: rimuovi i titoli auto non più promovibili
    # ---------------------------------------------------------------
    ticker_correnti = set(df_screener["Ticker"].str.upper().values)

    ticker_precedenti = set()
    if df_screener_precedente is not None and not df_screener_precedente.empty:
        ticker_precedenti = set(df_screener_precedente["Ticker"].str.upper().values)

    ticker_da_rimuovere = ticker_precedenti - ticker_correnti

    # Titoli auto nello screening corrente ma NON promovibili (fuori soglia)
    for _, row_s in df_screener.iterrows():
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
        min_dist = min(dist_poc, dist_vwap_4y, dist_vwap_1y, dist_vwap_3m)
        if min_dist > soglia_trigger_pct:
            ticker_da_rimuovere.add(ticker)

    # Rimuovo i titoli auto da rimuovere (solo se Origine=auto, mai i manuali)
    for ticker in ticker_da_rimuovere:
        if ticker in df_watchlist["Ticker"].str.upper().values:
            idx = df_watchlist[df_watchlist["Ticker"].str.upper() == ticker].index[0]
            origine = str(df_watchlist.at[idx, "Origine"]).strip().lower()
            if origine == "auto":
                df_watchlist = df_watchlist.drop(idx)
                rimossi += 1

    # ---------------------------------------------------------------
    # 3. COMMIT SU GITHUB
    # ---------------------------------------------------------------
    if aggiunti > 0 or rimossi > 0 or aggiornati > 0:
        commit_csv_su_github(df_watchlist)

    return {"aggiunti": aggiunti, "rimossi": rimossi, "aggiornati": aggiornati}
