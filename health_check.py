"""
health_check.py — Company Health Check (ARGO).
SOLO INDICAZIONE VISIVA: NON entra in selezione, soglie, graduatoria o watchlist.
3 cancelli: CRESCITA (ricavi YoY + trimestrale), CASSA (FCF + FCF margin),
SOLIDITÀ (debt/equity + current ratio).
Dato mancante = neutro (mai bocciare su assente). Cache su disco 24h
(i fondamentali sono trimestrali, refresh daily sarebbe spreco di chiamate).
"""

import json
import os
import time

import yfinance as yf

CACHE_PATH = "health_cache.json"
CACHE_TTL_SEC = 24 * 3600

MAPPA_BORSA_EUROPEA = {"CPR": "CPR.MI", "RI": "RI.PA", "NESN": "NESN.SW", "AF": "AF.PA"}

# --- manopole soglie -------------------------------------------------------
REV_VERDE, REV_GIALLO = 0.05, -0.05      # crescita ricavi YoY
QTR_VERDE, QTR_GIALLO = 0.10, -0.10      # crescita trimestrale
FCFM_VERDE = 0.05                        # FCF margin
DE_VERDE, DE_GIALLO = 100, 200           # debt/equity (in %, come da yfinance)
CR_VERDE, CR_GIALLO = 1.2, 0.9           # current ratio

VERDE, GIALLO, ROSSO, NEUTRO = "🟢", "", "🔴", "⚪"


def _simbolo(ticker: str) -> str:
    t = ticker.strip().upper()
    return MAPPA_BORSA_EUROPEA.get(t, t)


def _num(d: dict, chiave):
    try:
        v = d.get(chiave) if d else None
        if v is None:
            return None
        f = float(v)
        return f if f == f else None
    except Exception:
        return None


def _carica_cache() -> dict:
    if not os.path.exists(CACHE_PATH):
        return {}
    try:
        with open(CACHE_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _salva_cache(cache: dict):
    try:
        with open(CACHE_PATH, "w") as f:
            json.dump(cache, f)
    except Exception:
        pass


def _info_cached(ticker: str, cache: dict) -> dict:
    t = ticker.strip().upper()
    voce = cache.get(t)
    ora = time.time()
    if voce and (ora - voce.get("ts", 0)) < CACHE_TTL_SEC:
        return voce.get("info") or {}
    try:
        info = yf.Ticker(_simbolo(t)).info or {}
    except Exception:
        info = {}
    cache[t] = {"ts": ora, "info": info}
    return info


# --- semafori ---------------------------------------------------------------

def gate_crescita(rev_yoy, qtr):
    if rev_yoy is None and qtr is None:
        return NEUTRO, 0.5
    if rev_yoy is not
