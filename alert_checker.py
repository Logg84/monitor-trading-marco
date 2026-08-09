#!/usr/bin/env python3
"""
alert_checker.py – ARGO Alert Checker (esecuzione oraria via GitHub Actions)
Controlla i prezzi attuali dei titoli in watchlist e invia alert Telegram
se il prezzo tocca un POC o un VWAP entro la soglia configurata.
Blocca l'esecuzione nel weekend (sabato/dom).
"""

import os
import json
import datetime
import time
import requests
import pandas as pd
import yfinance as yf
from pathlib import Path

# ===================== CONFIGURAZIONE =====================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")

ALERT_COOLDOWN_DAYS = 3           # giorni di silenzio dopo un alert per lo stesso ticker
SOGLIA_TOcco_POC = 2.0            # % entro cui scatta l'alert POC
SOGLIA_TOcco_VWAP = 2.0           # % entro cui scatta l'alert VWAP
PREZZI_CORRENTI_FILE = "prezzi_attuali.json"
ALERT_HISTORY_FILE = "alert_history.json"
WATCHLIST_FILE = "watchlist.csv"

# ===================== UTILITÀ =====================

def e_weekend() -> bool:
    """Restituisce True se oggi è sabato o domenica."""
    oggi = datetime.date.today()
    return oggi.weekday() >= 5  # 5=sabato, 6=domenica


def log(msg: str):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")


def invia_telegram(messaggio: str):
    """Invia un messaggio Telegram. Non blocca in caso di errore."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log("⚠️ Token Telegram o Chat ID mancanti. Messaggio non inviato.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": messaggio, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code != 200:
            log(f"⚠️ Telegram ha risposto {r.status_code}: {r.text}")
    except Exception as e:
        log(f"⚠️ Errore invio Telegram: {e}")


def carica_json(nome_file: str) -> dict:
    """Carica un JSON dal disco, restituisce {} se non esiste."""
    if not Path(nome_file).exists():
        return {}
    try:
        with open(nome_file, "r") as f:
            return json.load(f)
    except Exception as e:
        log(f"⚠️ Errore lettura {nome_file}: {e}")
        return {}


def salva_json(nome_file: str, dati: dict):
    """Salva un JSON su disco."""
    try:
        with open(nome_file, "w") as f:
            json.dump(dati, f, indent=2)
    except Exception as e:
        log(f"⚠️ Errore scrittura {nome_file}: {e}")


def carica_watchlist() -> pd.DataFrame:
    """Carica la watchlist dal CSV."""
    if not Path(WATCHLIST_FILE).exists():
        log("⚠️ File watchlist.csv non trovato.")
        return pd.DataFrame()
    try:
        return pd.read_csv(WATCHLIST_FILE)
    except Exception as e:
        log(f"⚠️ Errore lettura {WATCHLIST_FILE}: {e}")
        return pd.DataFrame()


def ottieni_prezzo_corrente(ticker: str) -> float | None:
    """Scarica il prezzo corrente da Yahoo Finance."""
    try:
        t = yf.Ticker(ticker)
        # fast_info è più veloce, ma a volte non disponibile
        try:
            prezzo = t.fast_info.get('lastPrice', None)
        except Exception:
            prezzo = None
        if prezzo is None:
            info = t.info
            prezzo = info.get('regularMarketPrice') or info.get('currentPrice') or info.get('previousClose')
        if prezzo is not None:
            return float(prezzo)
        # fallback: scarica le ultime 2 barre daily
        hist = t.history(period="5d", interval="1d")
        if not hist.empty and 'Close' in hist.columns:
            return float(hist['Close'].dropna().iloc[-1])
    except Exception as e:
        log(f"⚠️ Errore download prezzo per {ticker}: {e}")
    return None


def calcola_distanza(prezzo: float, livello: float) -> float:
    """Distanza percentuale tra prezzo e livello."""
    if livello is None or livello == 0:
        return float('inf')
    return (prezzo - livello) / livello * 100


def check_alert_ticker(ticker: str, prezzo: float, row: pd.Series,
                       alert_history: dict, oggi_str: str) -> list[str]:
    """
    Controlla se il prezzo di un ticker tocca un POC o un VWAP entro soglia.
    Restituisce una lista di stringhe con i messaggi di alert.
    """
    avvisi = []

    # Controlla cooldown
    ultimo_alert = alert_history.get(ticker)
    if ultimo_alert:
        try:
            data_ultimo = datetime.date.fromisoformat(ultimo_alert)
            if (datetime.date.today() - data_ultimo).days < ALERT_COOLDOWN_DAYS:
                return []  # ancora in cooldown
        except ValueError:
            pass

    # POC (fino a 3)
    for i in range(1, 4):
        poc_key = f"POC {i}" if f"POC {i}" in row else f"POC{i}"
        poc_val = row.get(poc_key)
        if poc_val is None or pd.isna(poc_val) or float(poc_val) <= 0:
            continue
        poc_val = float(poc_val)
        dist = calcola_distanza(prezzo, poc_val)
        if abs(dist) <= SOGLIA_TOcco_POC:
            avvisi.append(
                f"🎯 <b>{ticker}</b> tocca POC {i} "
                f"({poc_val:.2f}) a {prezzo:.2f} "
                f"(distanza {dist:+.2f}%)"
            )

    # VWAP (3M, 1Y, 4Y)
    for label, key in [("VWAP 3M", "VWAP 3M"), ("VWAP 1Y", "VWAP 1Y"), ("VWAP 4Y", "VWAP 4Y")]:
        vwap_val = row.get(key)
        if vwap_val is None or pd.isna(vwap_val) or float(vwap_val) <= 0:
            continue
        vwap_val = float(vwap_val)
        dist = calcola_distanza(prezzo, vwap_val)
        if abs(dist) <= SOGLIA_TOcco_VWAP:
            avvisi.append(
                f"📊 <b>{ticker}</b> tocca {label} "
                f"({vwap_val:.2f}) a {prezzo:.2f} "
                f"(distanza {dist:+.2f}%)"
            )

    return avvisi


def commit_e_push(file_da_committare: list[str], messaggio: str):
    """Esegue git add, commit e push con strategia ours per evitare conflitti."""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        log("⚠️ Token GitHub o repo mancanti. Saltato commit.")
        return
    try:
        # Configura git
        os.system('git config user.name "alert-bot"')
        os.system('git config user.email "alert-bot@argo.local"')

        # Pull con strategia ours (in caso di conflitto vince il nostro)
        ret = os.system("git pull -X ours origin main")
        if ret != 0:
            log(f"⚠️ git pull uscito con codice {ret}, proseguo comunque.")

        # Add
        for f in file_da_committare:
            os.system(f"git add {f}")

        # Commit (solo se ci sono modifiche)
        ret = os.system(f'git commit -m "{messaggio}"')
        # 0 = successo, 1 = niente da committare, >1 = errore
        if ret == 1:
            log("ℹ️ Nessuna modifica da committare.")
            return

        # Push
        ret = os.system("git push origin main")
        if ret != 0:
            log(f"⚠️ git push uscito con codice {ret}")
        else:
            log("✅ Commit e push riusciti.")
    except Exception as e:
        log(f"⚠️ Errore durante commit/push: {e}")


# ===================== MAIN =====================

def main():
    log("🚀 ARGO Alert Checker avviato.")

    # ==================== BLOCCO WEEKEND ====================
    if e_weekend():
        log("⏸️ Oggi è weekend (sabato o domenica). Nessun alert verrà inviato. Ciao!")
        return
    # =======================================================

    # Carica watchlist
    df_wl = carica_watchlist()
    if df_wl.empty:
        log("⚠️ Watchlist vuota. Uscita.")
        return

    # Carica storico alert
    alert_history = carica_json(ALERT_HISTORY_FILE)

    # Carica prezzi attuali già salvati (per evitare download inutili)
    prezzi_salvati = carica_json(PREZZI_CORRENTI_FILE)

    oggi_str = datetime.date.today().isoformat()
    nuovi_alert = []       # messaggi completi da inviare
    ticker_alertati = []   # lista ticker per aggiornare cooldown
    prezzi_aggiornati = {} # per salvare i prezzi fresh

    for _, row in df_wl.iterrows():
        ticker = str(row.get("Ticker", "")).strip().upper()
        if not ticker:
            continue

        # Prezzo: prima da file salvato, poi download
        prezzo = prezzi_salvati.get(ticker)
        if prezzo is None:
            log(f"📡 Download prezzo per {ticker}...")
            prezzo = ottieni_prezzo_corrente(ticker)
            time.sleep(0.3)  # rate limiting Yahoo
        else:
            log(f"📦 Prezzo in cache per {ticker}: {prezzo}")

        if prezzo is None:
            log(f"⚠️ Impossibile ottenere prezzo per {ticker}, saltato.")
            continue

        prezzi_aggiornati[ticker] = prezzo

        # Controlla livelli
        avvisi = check_alert_ticker(ticker, prezzo, row, alert_history, oggi_str)
        if avvisi:
            nuovi_alert.extend(avvisi)
            ticker_alertati.append(ticker)

    # Salva i prezzi aggiornati
    salva_json(PREZZI_CORRENTI_FILE, prezzi_aggiornati)

    # Se ci sono alert, invia e aggiorna storico
    if nuovi_alert:
        # Aggiorna cooldown
        for t in ticker_alertati:
            alert_history[t] = oggi_str
        salva_json(ALERT_HISTORY_FILE, alert_history)

        # Invia messaggio Telegram (max 4000 caratteri)
        corpo = "\n".join(nuovi_alert)
        if len(corpo) > 4000:
            corpo = corpo[:3900] + "\n... (troncato)"
        log(f"📨 Invio {len(nuovi_alert)} alert Telegram...")
        invia_telegram(corpo)

        # Commit e push dei file aggiornati
        commit_e_push(
            [PREZZI_CORRENTI_FILE, ALERT_HISTORY_FILE],
            "Aggiorna prezzi, storico alert"
        )
    else:
        log("✅ Nessun nuovo alert da inviare.")
        # Committa comunque i prezzi aggiornati
        commit_e_push(
            [PREZZI_CORRENTI_FILE],
            "Aggiorna prezzi correnti"
        )

    log("🏁 ARGO Alert Checker terminato.")


if __name__ == "__main__":
    main()
