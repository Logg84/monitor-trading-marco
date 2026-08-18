"""
Modulo condiviso per la gestione della watchlist su GitHub.
Usato da app.py (portale alert) e pages/2_Screening.py (promozione auto).

REGOLA VWAP: i VWAP vengono rinfrescati SEMPRE (auto e manuali) a ogni run,
perché l'utente non li inserisce mai a mano. Livelli e POC manuali = sacri.
REGOLA PERMANENZA: un auto resta finché è in sconto (>=25% drawdown); viene
rimosso solo se esce dallo screening (zombie), NON se si allontana dal 2,5%.
La soglia 2,5% governa solo l'INGRESSO dei nuovi auto e gli alert.
REPORT: promuovi_auto_da_screener restituisce anche le LISTE dei ticker toccati
(aggiunti/aggiornati/vwappati) per il pannello di feedback della UI.

NUOVO: Zone POC (aree, non punti) - POC Low/High per ogni POC operativo.
"""

import os
import base64
import requests
import pandas as pd
import streamlit as st

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
CSV_PATH = "watchlist.csv"
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN") if hasattr(st, "secrets") else os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = st.secrets.get("GITHUB_REPO") if hasattr(st, "secrets") else os.environ.get("GITHUB_REPO")
_TEXT_COLS = {"Screenshot", "Origine", "Auto_Indice"}
_VWAP_LABELS = {"VWAP 4Y", "VWAP 1Y", "VWAP 3M"}


def _is_text_col(col: str) -> bool:
    return col.startswith("Nota") or col in _TEXT_COLS


def _github_request(url: str, headers: dict, timeout: int = 10) -> requests.Response | None:
    """Esegue una richiesta GitHub con timeout ridotto e gestisce gli errori."""
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        return r
    except (requests.exceptions.Timeout, requests.exceptions.TooManyRedirects,
            requests.exceptions.RequestException) as e:
        print(f"Errore richiesta GitHub: {e}")
        return None


def carica_watchlist_da_github() -> pd.DataFrame:
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return pd.DataFrame(columns=COLONNE_ATTESE)
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{CSV_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = _github_request(url, headers, timeout=8)  # timeout 8s invece di default
    if r is None or r.status_code != 200:
        print(f"Fallito fetch watchlist da GitHub (status={r.status_code if r else 'timeout'}), uso file locale")
        # Fallback: leggi file locale se esiste
        if os.path.exists(CSV_PATH):
            try:
                df = pd.read_csv(CSV_PATH)
                return df.rename(columns=ALIAS_COLONNE) if not df.empty else pd.DataFrame(columns=COLONNE_ATTESE)
            except Exception:
                return pd.DataFrame(columns=COLONNE_ATTESE)
        return pd.DataFrame(columns=COLONNE_ATTESE)
    try:
        contenuto = base64.b64decode(r.json()["content"]).decode()
        df = pd.read_csv(io.StringIO(contenuto))
    except Exception as e:
        print(f"Errore parsing watchlist da GitHub: {e}")
        # Fallback locale
        if os.path.exists(CSV_PATH):
            try:
                df = pd.read_csv(CSV_PATH)
                return df.rename(columns=ALIAS_COLONNE) if not df.empty else pd.DataFrame(columns=COLONNE_ATTESE)
            except Exception:
                return pd.DataFrame(columns=COLONNE_ATTESE)
        return pd.DataFrame(columns=COLONNE_ATTESE)
    df = df.rename(columns=ALIAS_COLONNE)
    for col in COLONNE_ATTESE:
        if col not in df.columns:
            df[col] = ""
    df = df[COLONNE_ATTESE]
    if "Origine" in df.columns:
        df["Origine"] = df["Origine"].fillna("manuale").replace("", "manuale")
    for col in COLONNE_ATTESE:
        if _is_text_col(col):
            df[col] = df[col].fillna("").astype(str).replace("nan", "")
    for col in ["Livello 1", "Livello 2", "Livello 3", "VWAP 1", "VWAP 2", "VWAP 3",
                "POC 1", "POC 2", "POC 3",
                "POC 1 Low", "POC 1 High", "POC 2 Low", "POC 2 High", "POC 3 Low", "POC 3 High"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0).astype(float)
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated()]
    return df


def commit_csv_su_github(df: pd.DataFrame):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        print("GITHUB_TOKEN o GITHUB_REPO non configurati, skip commit.")
        return
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{CSV_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = _github_request(url, headers, timeout=10)  # timeout 10s
    if r is None or r.status_code != 200:
        print(f"Fallito fetch per ottenere SHA su GitHub, skip commit")
        return
    sha = r.json().get("sha") if r.status_code == 200 else None
    contenuto_b64 = base64.b64encode(df.to_csv(index=False).encode()).decode()
    payload = {"message": "Aggiorna watchlist.csv (promozione auto + rinfresco VWAP)", "content": contenuto_b64, "branch": "main"}
    if sha:
        payload["sha"] = sha
    resp = requests.put(url, headers=headers, json=payload, timeout=10)
    if resp.status_code not in (200, 201):
        print(f"Commit watchlist su GitHub fallito: {resp.status_code} {resp.text[:200]}")


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


def promuovi_auto_da_screener(
    df_screener: pd.DataFrame,
    indice_corrente: str,
    soglia_trigger_pct: float = 2.5,
) -> dict:
    """Rinfresco VWAP sempre (auto+manuali); POC solo su auto; ingresso nuovi solo se in zona.
    NON rimuove più per 'fuori zona': la rimozione la fa pulisci_auto_zombie nel chiamante.
    Restituisce anche le liste dei ticker toccati, per il pannello di feedback.
    
    NUOVO: Zone POC - considera dentro zona se prezzo tra POC Low e POC High.
    """
    vuoto = {"aggiunti": 0, "rimossi": 0, "aggiornati": 0, "vwappati": 0, "in_zona": 0,
             "aggiunti_tickers": [], "aggiornati_tickers": [], "vwappati_tickers": []}
    if df_screener.empty:
        return vuoto

    df_watchlist = carica_watchlist_da_github()
    aggiunti, aggiornati, vwappati, in_zona = 0, 0, 0, 0
    aggiunti_t, aggiornati_t, vwappati_t = [], [], []

    def _write_vwap(target_df, idx, row_s):
        pairs = [("VWAP 1", "VWAP 4Y", "VWAP 4Y"),
                 ("VWAP 2", "VWAP 1Y", "VWAP 1Y"),
                 ("VWAP 3", "VWAP 3M", "VWAP 3M")]
        for col, src, label in pairs:
            target_df.at[idx, col] = _safe_float(row_s.get(src), 0.0)
            nota_col = "Nota " + col
            existing = str(target_df.at[idx, nota_col] or "").strip()
            if existing == "" or existing in _VWAP_LABELS:
                target_df.at[idx, nota_col] = label

    def _write_pocs(target_df, idx, row_s):
        """Scrive POC e zone (low/high) per i 3 POC operativi."""
        for k in (1, 2, 3):
            target_df.at[idx, f"POC {k}"] = _safe_float(row_s.get(f"POC {k}"), 0.0)
            target_df.at[idx, f"POC {k} Low"] = _safe_float(row_s.get(f"POC {k} Low"), 0.0)
            target_df.at[idx, f"POC {k} High"] = _safe_float(row_s.get(f"POC {k} High"), 0.0)
            target_df.at[idx, f"Nota POC {k}"] = str(row_s.get(f"Nota POC {k}", "") or "")
        target_df.at[idx, "Auto_Indice"] = indice_corrente

    def _dists(row_s, prezzo):
        """Calcola la distanza minima considerando zone POC e VWAP.
        Se il prezzo è dentro una zona POC, distanza = 0.
        Altrimenti calcola distanza % dal punto POC o VWAP più vicino."""
        # Controlla se il prezzo è dentro una zona POC
        for k in (1, 2, 3):
            poc_low = _safe_float(row_s.get(f"POC {k} Low"), 0.0)
            poc_high = _safe_float(row_s.get(f"POC {k} High"), 0.0)
            if poc_low > 0 and poc_high > 0 and poc_low <= prezzo <= poc_high:
                return 0.0  # dentro zona
        
        # Calcola distanza dai punti POC
        poc_vals = [_safe_float(row_s.get(f"POC {k}"), 0.0) for k in (1, 2, 3)]
        poc_vals = [v for v in poc_vals if v != 0]
        dist_poc = min(abs(prezzo - v) / v * 100 for v in poc_vals) if poc_vals else 999
        
        # Calcola distanza dai VWAP
        v4 = _safe_float(row_s.get("VWAP 4Y"), 0.0)
        v1 = _safe_float(row_s.get("VWAP 1Y"), 0.0)
        v3 = _safe_float(row_s.get("VWAP 3M"), 0.0)
        d4 = abs(prezzo - v4) / v4 * 100 if v4 != 0 else 999
        d1 = abs(prezzo - v1) / v1 * 100 if v1 != 0 else 999
        d3 = abs(prezzo - v3) / v3 * 100 if v3 != 0 else 999
        
        return min(dist_poc, d4, d1, d3)

    for _, row_s in df_screener.iterrows():
        ticker = str(row_s.get("Ticker", "")).strip().upper()
        if not ticker:
            continue
        prezzo = _safe_float(row_s.get("Prezzo"), 0.0)
        if prezzo == 0:
            continue
        if _dists(row_s, prezzo) <= soglia_trigger_pct:
            in_zona += 1

        mask = df_watchlist["Ticker"].str.upper() == ticker
        if mask.any():
            idx = df_watchlist[mask].index[0]
            origine = str(df_watchlist.at[idx, "Origine"]).strip().lower()
            _write_vwap(df_watchlist, idx, row_s)
            if origine == "manuale":
                vwappati += 1
                vwappati_t.append(ticker)
            else:
                _write_pocs(df_watchlist, idx, row_s)
                aggiornati += 1
                aggiornati_t.append(ticker)
        else:
            if _dists(row_s, prezzo) <= soglia_trigger_pct:
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
                    "Auto_Indice": indice_corrente,
                }])
                df_watchlist = pd.concat([df_watchlist, nuova], ignore_index=True)
                aggiunti += 1
                aggiunti_t.append(ticker)

    if aggiunti > 0 or aggiornati > 0 or vwappati > 0:
        commit_csv_su_github(df_watchlist)

    return {
        "aggiunti": aggiunti, "rimossi": 0, "aggiornati": aggiornati, "vwappati": vwappati, "in_zona": in_zona,
        "aggiunti_tickers": aggiunti_t, "aggiornati_tickers": aggiornati_t, "vwappati_tickers": vwappati_t,
    }
