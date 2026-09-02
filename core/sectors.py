"""
SETTORI — doppio livello, entrambi standard, niente famiglie inventate.

LIVELLO 1 · 11 settori GICS (S&P Dow Jones Indices / MSCI: 11 settori → 25
industry group → 74 industrie). Per ogni settore le due gambe sono due facce
delLO STESSO indice: Select Sector SPDR (a capitalizzazione) e Invesco S&P 500
Equal Weight di quel settore (pesi uguali) — stessi titoli. Il Δ che ne esce è
effetto della sola pesatura, non della composizione: è il motivo per cui la
spina del portale è GICS e non una classificazione fatta in casa.

LIVELLO 2 · sotto-settori S&P Select Industry (i "SPDR S&P <Industria>, indici
modified equal-weight by design) + temi che GICS non contiene (minatori d'oro,
uranio, solare, IA, agribusiness), tenuti in una tabella separata perché non
siano spacciati per categorie di classificazione.

REGOLA CHIAVE: il settore è CONTESTO, mai segnale. Non tocca i punti 0-6 di
`reversal_state` (cancello A e punti identici alle specifiche di consegna), non
entra in `prune_watchlist` né in `auto_populate`, non modifica chiavi di dedup
o cooldown degli alert. Produce etichetta, stato 0-100, Δ EW−CW, nota di vento
e Priorità (Bottom + bonus settore ±10), che serve a ORDINARE, non a decidere.

Punteggio di settore (0-100, pesi fissi e dichiarati):
  25% trend (sopra SMA50 / SMA200 della gamba cw) · 25% momentum 3m ·
  15% momentum 6m · 15% forza relativa 3m vs SPY · 10% posizione su 52 sett. ·
  10% breadth (Δ EW−CW a 3m)
Senza gamba EW il termine di breadth vale neutro (0.5) e in UI compare "—":
"n/d" NON è "neutro".

Stato del dato in 3 livelli dichiarati: live → cache del repo
(data/sectors_latest.json, committata dalla CI) → "n/d". Una cache di formato
precedente viene RIFIUTATA (vedi _CACHE_KEYS), non parsata a metà.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SECTORS_CACHE_JSON = DATA_DIR / "sectors_latest.json"
SECTOR_MAP_JSON = DATA_DIR / "sector_map.json"

BENCHMARK = "SPY"        # mercato cap-weighted
BENCHMARK_EW = "RSP"     # mercato equal-weighted (breadth di sistema)
MIN_BARS = 60            # barre minime per chiamare uno stato

# ── Registro: 11 settori GICS (spina ufficiale, non inventata) ──────
# GICS (S&P Dow Jones Indices / MSCI): 11 settori → 25 industry group →
# 74 industrie. È la scelta giusta per il confronto CW vs EW perché le due
# gambe sono DUE FACCE DELLO STESSO INDICE: il Select Sector SPDR (a
# capitalizzazione) e l'Invesco S&P 500 Equal Weight di quel settore pesano
# gli IDENTICI titoli. Il Δ che ne esce è effetto di pesatura puro, non di
# composizione diversa — cosa che con accorpamenti arbitrariti non garantivi.
#
# cw = capitalizzazione, ew = pesi uguali. `gics` = numero di codice del
# settore (usato nei dati di mercato, utile se un domani leggi un file GICS).
SECTORS: dict[str, dict] = {
    "tech":            {"label": "Information Technology",  "gics": 45, "cw": "XLK",  "ew": "RSPT"},
    "finanziario":     {"label": "Financials",              "gics": 40, "cw": "XLF",  "ew": "RSPF"},
    "sanita":          {"label": "Health Care",             "gics": 35, "cw": "XLV",  "ew": "RSPH"},
    "industriale":     {"label": "Industrials",             "gics": 20, "cw": "XLI",  "ew": "RSPN"},
    "consumi_disc":    {"label": "Consumer Discretionary",  "gics": 25, "cw": "XLY",  "ew": "RSPD"},
    "consumi_staples": {"label": "Consumer Staples",        "gics": 30, "cw": "XLP",  "ew": "RSPS"},
    "materiali":       {"label": "Materials",               "gics": 15, "cw": "XLB",  "ew": "RSPM"},
    "energia":         {"label": "Energy",                  "gics": 10, "cw": "XLE",  "ew": "RSPG"},
    "utilities":       {"label": "Utilities",               "gics": 55, "cw": "XLU",  "ew": "RSPU"},
    "immobiliare":     {"label": "Real Estate",             "gics": 60, "cw": "XLRE", "ew": "RSPR"},
    "comunicazioni":   {"label": "Communication Services",  "gics": 50, "cw": "XLC",  "ew": "RSPC"},
}

# ── Sotto-settori S&P Select Industry (layer standard sotto il settore) ─
# I "SPDR S&P <Industria>" sono indice S&P Select Industry = modified
# equal-weight by design. Il gemello a capitalizzazione esiste SOLO per
# alcuni: dove non c'è, la breadth è n/d (mai messa a zero, mai inventata).
# `gics` = settore di appartenenza: non è una mia famiglia, è la mappa GICS
# (es. Aerospace & Defense sta in Industrials, Transportation in Industrials).
SUBSECTORS: dict[str, dict] = {
    "semiconduttori": {"label": "Semiconduttori & equipaggiamento", "gics": "tech",
                       "cw": "SOXX", "ew": "XSD"},
    "software":       {"label": "Software & servizi IT", "gics": "tech",
                       "cw": "IGV", "ew": "XSW"},
    "hardware":       {"label": "Hardware tecnologico", "gics": "tech",
                       "cw": "FDN", "ew": None},
    "farmaci":        {"label": "Farmaceutici", "gics": "sanita",
                       "cw": "PPH", "ew": "XPH"},
    "biotech":        {"label": "Biotecnologie", "gics": "sanita",
                       "cw": "IBB", "ew": "XBI"},
    "dispositivi":    {"label": "Dispositivi medici", "gics": "sanita",
                       "cw": None, "ew": "XHE"},
    "servizi_sanita": {"label": "Servizi sanitari (payer, ospedali)", "gics": "sanita",
                       "cw": None, "ew": "XHS"},
    "banche":         {"label": "Banche", "gics": "finanziario",
                       "cw": None, "ew": "KBE"},
    "regional_banks": {"label": "Banche regionali", "gics": "finanziario",
                       "cw": None, "ew": "KRE"},
    "assicurazioni":  {"label": "Assicurazioni", "gics": "finanziario",
                       "cw": None, "ew": "KIE"},
    "mercati_capitali": {"label": "Mercati capitali (broker, AM, exchanges)",
                         "gics": "finanziario", "cw": None, "ew": "KCE"},

    "distribuzione":  {"label": "Distribuzione & retail (tutti i formati)",
                       "gics": "consumi_disc", "cw": "RTH", "ew": "XRT",
                       "note": "RTH è il paniere retail a capitalizzazione, XRT "
                               "lo stesso universo a pesi uguali: qui il Δ è "
                               "pulito"},
    "cibo_bevande":   {"label": "Cibo, bevande & tabacco", "gics": "consumi_staples",
                       "cw": None, "ew": None},
    "gas_e_p":        {"label": "Petrolio & gas (E&P, integrati, servizi)",
                       "gics": "energia", "cw": "XLE", "ew": "XOP",
                       "note": "XOP è l'equal-weighted del solo sottogruppo E&P, "
                              "XLE il settore intero: il Δ qui mescola perimetri "
                              "diverso, si usa come lettura di energia "
                              "'a monte' vs settore"},
    "capital_goods":  {"label": "Beni strumentali & macchinari", "gics": "industriale",
                       "cw": "XLI", "ew": None},
    "aero_difesa":    {"label": "Aerospazio & difesa", "gics": "industriale",
                       "cw": "ITA", "ew": "XAR"},
    "trasporti":      {"label": "Trasporti", "gics": "industriale",
                       "cw": "IYT", "ew": None},
    "edilizia_casa":  {"label": "Costruzioni case", "gics": "consumi_disc",
                       "cw": "ITB", "ew": "XHB"},
    "chimica":        {"label": "Chimica", "gics": "materiali", "cw": None, "ew": None},
    "metalli_minere": {"label": "Metalli & miniere", "gics": "materiali",
                       "cw": None, "ew": "XME"},
    "moda_lusso":     {"label": "Abbigliamento & lusso", "gics": "consumi_disc",
                       "cw": None, "ew": None},
    "media_intratten": {"label": "Media & intrattenimento", "gics": "comunicazioni",
                        "cw": None, "ew": None},
    "telecom":        {"label": "Telecomunicazioni", "gics": "comunicazioni",
                       "cw": None, "ew": None},
    "REIT":           {"label": "REIT", "gics": "immobiliare",
                       "cw": "VNQ", "ew": None},
    "prodotti_persona": {"label": "Casa, toeletta & bellezza", "gics": "consumi_staples",
                         "cw": None, "ew": None},
    "utility_regolate": {"label": "Utility regolate (elettrico, gas, acqua)",
                         "gics": "utilities", "cw": None, "ew": None,
                         "note": "nessun ETF dedicato su questo sotto-settore: la "
                                 "lettura passa dal settore Utilities (livello 1)"},
    "tempo_libero":      {"label": "Ristoranti & tempo libero", "gics": "consumi_disc",
                       "cw": None, "ew": None},
    "auto_componenti": {"label": "Auto & componenti", "gics": "consumi_disc",
                        "cw": None, "ew": None},
}

# Temi CHE NON SONO categorie GICS: nessuna pretesa di coppia CW/EW. Stanno
# in una tabella separata proprio per non sporcare la tassonomia.
THEMES: dict[str, dict] = {
    "oro":        {"label": "Minatori d'oro",        "cw": "GDX", "ew": None},
    "uranio":     {"label": "Uranio & nucleare",     "cw": "URA", "ew": None},
    "solare":     {"label": "Solare",                "cw": "TAN", "ew": None},
    "clean_energy": {"label": "Energia pulita",      "cw": "ICLN", "ew": None},
    "robotica":   {"label": "Robotica & automazione","cw": "ROBO", "ew": None},
    "ai_th":      {"label": "Intelligenza artificiale", "cw": "BOTZ", "ew": None},
    "agro":       {"label": "Agribusiness",          "cw": "MOO", "ew": None},
    "soft_agri":  {"label": "Materie prime agricole (futures)", "cw": "TAGS", "ew": None},
    "rame":       {"label": "Rame",                  "cw": "COPX", "ew": None},}

# Parole chiave su "industria · settore" normalizzati (Yahoo li mette in inglese
# anche per le quotate europee: "Drug Manufacturers—Specialty & Generic" ecc.).
# Ordine = dal tema specifico al generale: la prima corrispondenza vince, quindi
# le regole fini (chip, software, banche) stanno prima di quelle ampie.
# ── Titolo → tassonomia ────────────────────────────────────
# Livello 1 (settore GICS): Yahoo espone già il settore GICS nel campo
# "sector" ("Technology", "Healthcare", "Financial Services"...): niente
#.classifiche casalinghe, è il campo del fornitore.
GICS_BY_YAHOO = {
    "Technology": "tech", "Healthcare": "sanita", "Financial Services": "finanziario",
    "Financials": "finanziario", "Industrials": "industriale",
    "Consumer Cyclical": "consumi_disc", "Consumer Defensive": "consumi_staples",
    "Basic Materials": "materiali", "Utilities": "utilities",
    "Real Estate": "immobiliare", "Communication Services": "comunicazioni",
    "Energy": "energia", "Consumer Electronics": "consumi_disc",
}
# Se il campo sector manca, ultime ancora sulle parole del settore.
GICS_PAROLE = (("technolog", "tech"), ("financ", "finanziario"), ("health", "sanita"),
               ("industr", "industriale"), ("defensive", "consumi_staples"),
               ("cyclical", "consumi_disc"), ("material", "materiali"),
               ("utilit", "utilities"), ("real estate", "immobiliare"),
               ("communication", "comunicazioni"), ("energy", "energia"))

# Livello 2 (sotto-settore): dal campo "industry" (sempre GICS, è il terzo
# livello della classificazione). Parole → chiave di SUBSECTORS.
SUB_RULES: list[tuple[tuple[str, ...], str]] = [
    (("semiconductor",), "semiconduttori"),
    (("software", "internet content", "information technology", "data processing"), "software"),
    (("technology hardware", "computer hardware", "communication equipment",
      "electronic components", "scientific technical instruments"), "hardware"),
    (("drug manufacturer", "pharmaceutical"), "farmaci"),
    (("biotech", "diagnostic", "medical research", "clinical research",
      "genomics"), "biotech"),
    (("medical device", "medical equipment", "medical instruments",
      "life sciences tools"), "dispositivi"),
    (("medical care", "health plan", "healthcare plans", "hospital",
      "health information services", "medical distribution"), "servizi_sanita"),
    (("banks", "savings", "credit union"), "banche"),
    (("regional banks",), "regional_banks"),
    (("insurance", "reinsurance"), "assicurazioni"),
    (("capital markets", "asset management", "brokers", "exchanges",
      "financial data", "stock exchanges", "specialty finance"), "mercati_capitali"),
    (("credit services", "consumer finance", "issuing lending", "credit cards"),
     "mercati_capitali"),
    (("oil gas exploration production", "oil gas e p", "petroleum", "drilling",
      "oil gas integrated", "refining marketing", "oil gas equipment services",
      "oil gas pipeline storage", "coal"), "gas_e_p"),
    (("aerospace defense", "defense", "space"), "aero_difesa"),
    (("railroads", "trucking", "airlines", "marine transportation", "passenger",
      "cargo ground transportation", "transportation infrastructures"), "trasporti"),
    (("reit", "real estate"), "REIT"),
    (("machinery", "construction machines", "farm construction machinery",
      "electrical equipment",
      "general building", "diversified industrials", "waste",
      "construction engineering", "consulting services", "professional services",
      "security protection services", "building products"), "capital_goods"),
    (("residential construction", "homebuilding", "home construction"), "edilizia_casa"),
    (("chemicals", "specialty chemicals", "agricultural chemicals"), "chimica"),
    (("copper", "metal mining", "diversified metals", "steel", "aluminum",
      "gold", "silver", "precious metals", "coal & consumable fuels"),
     "metalli_minere"),
    (("gold", "silver", "precious metals"), "metalli_minere"),
    (("food distributors", "grocery stores", "farm products", "poultry",
      "packaged foods", "beverages", "tobacco", "brewer"), "cibo_bevande"),
    (("apparel", "footwear", "luxury", "textiles", "furnishings"), "moda_lusso"),
    (("broadcasting", "publishing", "entertainment", "electronic gaming multimedia",
      "advertising", "movie production"), "media_intratten"),
    (("telecom", "wireless", "integrated telecommunication"), "telecom"),
    (("reit", "real estate"), "REIT"),
    (("household", "personal products", "consumer staples"), "prodotti_persona"),
    (("restaurants", "leisure", "gambling", "lodging"), "tempo_libero"),
    (("automotive", "auto manufacturers", "auto parts"), "auto_componenti"),
    (("utilities - ", "power utility", "regulated electric", "regulated gas",
      "regulated water", "water utility", "independent power", "gas utility",
      "diversified utilities", "multi utilities", "nuclear power generation"),
     "utility_regolate"),
    (("discount stores", "home improvement retail", "general merchandise",
      "specialty retail", "internet retail", "department retail", "distribution"),
     "distribuzione"),
]
# Sotto-settori che non sono un livello GICS ma vengono letti lo stesso (temi):
TEMA_REGOLE = ((("uranium", "nuclear"), "uranio"), (("solar",), "solare"),
               (("clean energy", "renewable", "wind", "hydrogen", "battery"), "clean_energy"),
               (("robotic", "artificial intelligence", "automation"), "robotica"),
               (("agriculture", "farming", "feeder cattle", "grain"), "agro"),
               (("copper",), "rame"), (("gold", "precious metals", "silver"), "oro"))
# ── Prezzi e gambe ─────────────────────────────────────────
def spec_of(key: str) -> dict | None:
    """Spec del registro chiave (settore GICS, sotto-settore o tema)."""
    for reg in (SECTORS, SUBSECTORS, THEMES):
        if key in reg:
            return reg[key]
    return None

def livello_of(key: str) -> str:
    return ("settore" if key in SECTORS else
            "sotto-settore" if key in SUBSECTORS else
            "tema" if key in THEMES else "n/d")

def _l(v) -> list[str]:
    if not v:
        return []
    return [v] if isinstance(v, str) else list(v)

def legs(key: str, side: str) -> list[str]:
    spec = spec_of(key) or {}
    return _l(spec.get(side))

def parent(key: str) -> str | None:
    spec = spec_of(key) or {}
    return spec.get("gics")

def all_keys() -> list[str]:
    return list(SECTORS) + list(SUBSECTORS) + list(THEMES)

def etf_universe() -> list[str]:
    """Benchmark + tutte le gambe cw/ew dei tre registri."""
    out = {BENCHMARK, BENCHMARK_EW}
    for k in all_keys():
        out.update(legs(k, "cw"))
        out.update(legs(k, "ew"))
    return sorted(out)

def _close_column(raw: pd.DataFrame, ticker: str) -> pd.Series | None:
    """Chiusure di un ticker da un frame di yf.download: MultiIndex in entrambi
    gli ordini (Field,Ticker)/(Ticker,Field), frame con colonna=ticker (è
    l'output di etf_closes) e frame con i campi (query a un solo ticker)."""
    if raw is None or raw.empty:
        return None
    if isinstance(raw.columns, pd.MultiIndex):
        for level in (0, 1):
            try:
                if ticker not in raw.columns.get_level_values(level):
                    continue
                sub = raw.xs(ticker, axis=1, level=level)
            except Exception:
                continue
            if isinstance(sub.columns, pd.MultiIndex):
                try:
                    out = sub["Close"]
                except Exception:
                    continue
            else:
                out = sub["Close"] if "Close" in sub.columns else (
                    sub.iloc[:, 0] if sub.shape[1] else None)
            if out is not None:
                return out
        return None
    if ticker in raw.columns:
        return raw[ticker]
    return raw["Close"] if "Close" in raw.columns else None

@st.cache_data(ttl=3600, show_spinner=False)
def etf_closes(tickers: tuple) -> pd.DataFrame:
    """Chiusure giornaliere di 1 anno, colonne = ticker. Cache 1 ora, una batch
    sola (i ~40 ETF dei tre registri costano una richiesta)."""
    cols = {}
    for i in range(0, len(tickers), 40):
        block = list(tickers[i:i + 40])
        try:
            raw = yf.download(block, period="1y", interval="1d",
                              auto_adjust=True, progress=False, threads=True)
        except Exception:
            continue
        if raw is None or raw.empty:
            continue
        if not isinstance(raw.columns, pd.MultiIndex) and len(block) > 1:
            continue  # colonne anonyme: meglio nulla che prezzi attribuiti a caso
        for t in block:
            c = _close_column(raw, t)
            if c is not None:
                cols[t] = c
    if not cols:
        raise ValueError("Download ETF di settore fallito")
    df = pd.DataFrame(cols).sort_index()
    df.index = pd.to_datetime(df.index)
    return df.dropna(how="all")

# ── Metriche di una gamba ──────────────────────────────────
def _mom(close: pd.Series, bars: int) -> float | None:
    s = close.dropna()
    if len(s) <= bars:
        return None
    base = float(s.iloc[-1 - bars])
    if base <= 0:
        return None
    return (float(s.iloc[-1]) / base - 1.0) * 100.0

def _pos_range(close: pd.Series, bars: int = 252) -> float | None:
    s = close.dropna().tail(bars)
    if len(s) < MIN_BARS:
        return None
    hi, lo = float(s.max()), float(s.min())
    if hi <= lo:
        return 50.0
    return (float(s.iloc[-1]) - lo) / (hi - lo) * 100.0

def _clip01(x: float) -> float:
    return float(np.clip(x, 0.0, 1.0))

def leg_stats(close: pd.Series, bench: pd.Series) -> dict:
    s = close.dropna()
    out = {"last": None, "sma50": None, "sma200": None, "above50": None,
           "mom21": None, "mom63": None, "mom126": None, "pos52": None,
           "rs63": None}
    if s.empty:
        return out
    out["last"] = float(s.iloc[-1])
    if len(s) >= 50:
        out["sma50"] = float(s.rolling(50).mean().iloc[-1])
        out["above50"] = bool(out["last"] > out["sma50"])
    if len(s) >= 200:
        out["sma200"] = float(s.rolling(200).mean().iloc[-1])
    out["mom21"] = _mom(s, 21)
    out["mom63"] = _mom(s, 63)
    out["mom126"] = _mom(s, 126) if len(s) > 126 else None
    out["pos52"] = _pos_range(s)
    b = bench.reindex(s.index).dropna()
    bm = _mom(b, 63) if len(b) > 63 else None
    if out["mom63"] is not None and bm is not None:
        out["rs63"] = out["mom63"] - bm
    return out

def _streak(series: pd.Series, ref: pd.Series) -> int | None:
    """Sedute consecutive in cui `series` sta sopra `ref` (+) o sotto (−):
    'da quanto' dura il vantaggio, non solo quanto vale."""
    cmp = (series > ref).dropna()
    if cmp.empty:
        return None
    last = bool(cmp.iloc[-1])
    n = 0
    for v in reversed(cmp.to_numpy()):
        if bool(v) != last:
            break
        n += 1
    return n if last else -n

# ── Stato di settore ───────────────────────────────────────
STATI = [("FORTE", "🚀"), ("IN MIGLIORAMENTO", "📈"), ("NEUTRO", "↔️"),
         ("DEBOLE", "⚠️"), ("IN CALO", "🔻"), ("n/d", "⚪")]

def stato_of(score: float | None, mom63: float | None,
             above50: bool | None) -> tuple[str, str]:
    """(stato, emoji). 'n/d' è diverso da 'neutro': nessun dato ≠ mercato piatto."""
    if score is None or mom63 is None or above50 is None:
        return "n/d", "⚪"
    if score >= 65 and mom63 > 0:
        return "FORTE", "🚀"
    if score >= 50:
        return "IN MIGLIORAMENTO", "📈"
    if score >= 35:
        return "NEUTRO", "↔️"
    if score >= 20:
        return "DEBOLE", "⚠️"
    return "IN CALO", "🔻"

def _metrics_for(closes: pd.DataFrame, key: str, bench: pd.Series) -> dict:
    """Stato di una unita dei tre registri. Gamba di lettura (quella da cui
    derivano punteggio, stato e direzione) è la cw se esiste, altrimenti la ew:
    un sotto-settore come i metalli esiste solo equal-weighted, quindi il trend
    si misura, la breadth no."""
    spec = spec_of(key) or {}
    cw_t, ew_t = _l(spec.get("cw")), _l(spec.get("ew"))
    ref_t = cw_t or ew_t  # il genitore GICS sta in spec["gics"]
    ref_c = _close_column(closes, ref_t[0]) if ref_t else None
    alt_c = _close_column(closes, ew_t[0]) if (ew_t and cw_t) else None
    ref_is_cw = bool(cw_t)
    a = leg_stats(ref_c if ref_c is not None else pd.Series(dtype=float), bench)
    b = leg_stats(alt_c, bench) if alt_c is not None else None
    ok = ref_c is not None and len(ref_c.dropna()) >= MIN_BARS
    d21 = d63 = d126 = None
    streak = pos_ratio = consist = None
    # momentum delle DUE gambe, nominate (non "riferimento/altro"): una tabella
    # deve poter mostrare CW 3m ed EW 3m affiancati a prescindere da quale delle
    # due sia usata per punteggio e direzione.
    cw_mom = {w: None for w in (21, 63, 126)}
    ew_mom = {w: None for w in (21, 63, 126)}
    for w in (21, 63, 126):
        v_ref, v_alt = a.get(f"mom{w}"), (b or {}).get(f"mom{w}")
        if ref_is_cw:
            cw_mom[w], ew_mom[w] = v_ref, v_alt
        else:
            ew_mom[w], cw_mom[w] = v_ref, v_alt
    if b is not None:
        for w in (21, 63, 126):
            x, y = b.get(f"mom{w}"), a.get(f"mom{w}")
            if x is not None and y is not None:
                v = x - y
                if w == 21: d21 = v
                elif w == 63: d63 = v
                else: d126 = v
        if ref_c is not None and alt_c is not None:
            # rapporto SEMPRE EW/CW: >1 i pesi uguali guadagnano sul CW
            ratio = (alt_c / ref_c) if ref_is_cw else (ref_c / alt_c)
            ratio = ratio.dropna()
            if len(ratio) >= 5:
                sma = ratio.rolling(20, min_periods=5).mean()
                streak = _streak(ratio, sma)
                pos_ratio = _pos_range(ratio)
                tail = (ratio > sma).tail(63)
                consist = float(tail.mean() * 100.0) if tail.size else None
    spread = d63  # termine di breadth del punteggio

    score = None
    if ok and a["mom63"] is not None and a["above50"] is not None:
        trend = (1 if a["above50"] else 0) + \
                (1 if (a["sma200"] and a["last"] > a["sma200"]) else 0)
        breadth_n = 0.5 if spread is None else _clip01(0.5 + spread / 20.0)
        score = round(100 * (
            0.25 * (trend / 2.0)
            + 0.25 * _clip01(0.5 + (a["mom63"] or 0.0) / 30.0)
            + 0.15 * _clip01(0.5 + (a["mom126"] or 0.0) / 60.0)
            + 0.15 * _clip01(0.5 + (a["rs63"] or 0.0) / 20.0)
            + 0.10 * ((a["pos52"] if a["pos52"] is not None else 50.0) / 100.0)
            + 0.10 * breadth_n), 1)

    stato, emoji = stato_of(score, a["mom63"] if ok else None,
                            a["above50"] if ok else None)
    dirz = "n/d"
    if score is not None:
        dirz = ("in crescita" if (a["mom63"] or 0) > 0 and a["above50"]
                else "in calo" if (a["mom63"] or 0) < 0 and a["above50"] is False
                else "laterale")
    acc = (a["mom21"] - a["mom63"] / 3.0) if ok and a["mom21"] is not None \
        and a["mom63"] is not None else None
    guida = "n/d"
    if d63 is not None:
        guida = ("pesi uguali (partecipazione diffusa)" if d63 > 1
                 else "capitalizzazione (trascinano i big)" if d63 < -1
                 else "equilibrato")
    if cw_t and ew_t:
        lettura = "CW + EW (Δ calcolabile)"
    elif cw_t:
        lettura = "solo CW (nessun equal-weighted sullo stesso perimetro)"
    elif ew_t:
        lettura = "solo EW (nessun cap-weighted sullo stesso perimetro)"
    else:
        lettura = "nessun paniere dedicato: lettura dal settore GICS"
    return {"chiave": key, "label": spec.get("label", key), "lettura": lettura,
            "livello": livello_of(key), "gics": spec.get("gics"),
            "cw": " · ".join(cw_t) or None, "ew": " · ".join(ew_t) or None,
            "riferimento": "cw" if ref_is_cw else "ew",
            "note": spec.get("note"),
            "score": score, "stato": stato, "emoji": emoji, "dir": dirz,
            "mom21": a["mom21"], "mom63": a["mom63"], "mom126": a["mom126"],
            "rs63": a["rs63"], "pos52": a["pos52"],
            "above50": a["above50"],
            "above200": bool(a["sma200"] and a["last"] > a["sma200"]) if ok else None,
            "d21": d21, "d63": d63, "d126": d126, "spread": spread, "acc": acc,
            "streak": streak, "pos_ratio": pos_ratio,
            "consistenza": round(consist, 0) if consist is not None else None,
            "guida": guida, "last": a["last"],
            "cw_mom21": cw_mom[21], "cw_mom63": cw_mom[63], "cw_mom126": cw_mom[126],
            "ew_mom21": ew_mom[21], "ew_mom63": ew_mom[63], "ew_mom126": ew_mom[126],
            "cw_stats": cw_mom, "ew_stats": ew_mom}

@st.cache_data(ttl=3600, show_spinner=False)
def sector_snapshot() -> dict | None:
    """Snapshot live dei tre registri + cache su disco (fallback della CI)."""
    try:
        closes = etf_closes(tuple(etf_universe()))
        bench = _close_column(closes, BENCHMARK)
        if bench is None or bench.dropna().empty:
            raise ValueError("benchmark SPY non disponibile")
        rows = {k: _metrics_for(closes, k, bench) for k in all_keys()}
        serie = bench.dropna()
        snap = {"saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                # `asof` = ultima chiusura realmente presente nei dati: dice DI
                # QUALE sessione sono i numeri, non quando sono stati scaricati
                "asof": str(serie.index[-1].date()) if len(serie) else None,
                "market_open_bar": bool(len(serie)
                                         and serie.index[-1].date() ==
                                         datetime.now(timezone.utc).date()),
                "benchmark": BENCHMARK, "benchmark_ew": BENCHMARK_EW,
                "bench_mom21": _mom(bench, 21), "bench_mom63": _mom(bench, 63),
                "bench_mom126": _mom(bench, 126), "rows": rows,
                "settori": list(SECTORS), "sotto": list(SUBSECTORS),
                "temi": list(THEMES)}
        _write_cache(snap)
        return snap
    except Exception:
        return None

def _write_cache(snap: dict) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SECTORS_CACHE_JSON.write_text(json.dumps(snap, ensure_ascii=False))
    except Exception:
        pass

# Firma strutturale: una cache di formato precedente viene RIFIUTATA (i campi
# Δ/consistenza mancanti verrebbero letti come 0 = "breadth neutra").
_REQ_ROW_KEYS = ("chiave", "label", "livello", "gics", "score", "stato", "dir",
                 "mom63", "spread", "d21", "d63", "d126", "cw_mom63", "ew_mom63",
                 "consistenza", "streak", "guida", "cw", "ew", "riferimento",
                 "lettura", "pos_ratio", "pos52", "acc")

def load_sector_cache() -> dict | None:
    try:
        if not SECTORS_CACHE_JSON.exists():
            return None
        data = json.loads(SECTORS_CACHE_JSON.read_text())
        rows = data.get("rows") or {}
        if not rows:
            return None
        if any(k not in r for r in rows.values() for k in _REQ_ROW_KEYS):
            return None
        return data
    except Exception:
        return None

def cache_age_hours(snap: dict | None) -> float | None:
    if not snap or not snap.get("saved_at"):
        return None
    try:
        t = datetime.fromisoformat(str(snap["saved_at"]))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - t).total_seconds() / 3600.0
    except Exception:
        return None

def freschezza(snap: dict | None, live: bool) -> str:
    """Riga unica che dichiara il dato: che sessione è, quanto è vecchia, se è
    live o cache. 'cache CI' con 30 ore non è la stessa cosa di un download
    appena fatto, e una barra intraday non è una chiusura."""
    if not snap:
        return "nessun dato (n/d): non è 'neutro', è assente"
    asof = snap.get("asof") or "n/d"
    eta = cache_age_hours(snap)
    eta_txt = "n/d" if eta is None else (f"{eta:.1f} h fa" if eta < 48
                                         else f"{eta / 24:.1f} gg fa")
    barra = ("barra di oggi ancora parziale" if snap.get("market_open_bar")
             else "chiusura consolidata")
    return (f"chiusura {asof} ({barra}) · snapshot {eta_txt} · "
            + ("live (cache 1 ora)" if live else "cache del repo (job CI)"))

def snapshot_and_source() -> tuple[dict | None, str]:
    """(snapshot, 'live' | 'cache CI' | 'n/d'): la cache è dichiarata, mai
    spacciata per dato fresco (è vecchia di un giorno o più)."""
    snap = sector_snapshot()
    src = "live"
    if snap is None:
        snap = load_sector_cache()
        src = "cache CI"
    if snap is None:
        return None, "n/d"
    age = cache_age_hours(snap)
    if age is None or age >= 6:
        src = "cache CI"
    return snap, src

def _rows_of(snapshot: dict | None, keys: list[str]) -> dict:
    rows = (snapshot or {}).get("rows", {})
    return {k: rows[k] for k in keys if k in rows}

def sector_rows() -> tuple[dict, str]:
    """Livello 1: gli 11 settori GICS (+ sorgente del dato)."""
    snap, src = snapshot_and_source()
    return _rows_of(snap, list(SECTORS)), src

def sub_rows() -> tuple[dict, str]:
    """Livello 2: sotto-settori S&P Select Industry."""
    snap, src = snapshot_and_source()
    return _rows_of(snap, list(SUBSECTORS)), src

def theme_rows() -> tuple[dict, str]:
    """Temi che non sono categorie di classificazione (oro, uranio, solare…)."""
    snap, src = snapshot_and_source()
    return _rows_of(snap, list(THEMES)), src

def all_rows() -> tuple[dict, str]:
    snap, src = snapshot_and_source()
    return _rows_of(snap, all_keys()), src

# ── Titolo → tassonomia ────────────────────────────────────
def _norm(x) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(x or "").lower())

def _match(parole: tuple, blob: str) -> str | None:
    return next((k for k in parole if k in blob), None)

def classify(sector: str | None, industry: str | None) -> tuple[str | None, str | None, str | None]:
    """(settore GICS, sotto-settore, tema) da campi settore/industria di Yahoo.
    Il settore viene DAL CAMPO del fornitore (che è GICS), non da una mia
    classificazione: se il campo manca si ripiega sulle parole, e solo dopo
    sul sotto-settore (che ha un `gics` di appartenenza)."""
    ind, sec = _norm(industry), _norm(sector)
    if not (ind or sec):
        return None, None, None
    sotto = next((k for parole, k in SUB_RULES if any(_norm(w) in ind for w in parole)), None)
    tema = next((k for parole, k in TEMA_REGOLE if any(_norm(w) in ind for w in parole)), None)
    gics = None
    for nome, chiave in GICS_BY_YAHOO.items():
        if _norm(nome) == sec.replace("  ", " ").strip():
            gics = chiave
            break
    if gics is None:
        for nome, chiave in GICS_BY_YAHOO.items():
            if _norm(nome) and _norm(nome) in sec:
                gics = chiave
                break
    if gics is None:
        gics = next((k for parole, k in GICS_PAROLE if parole in sec), None)
    if gics is None and sotto:
        gics = parent(sotto)
    if gics is None and tema:
        gics = parent(tema)
    return (gics if gics in SECTORS else None,
            sotto if sotto in SUBSECTORS else None,
            tema if tema in THEMES else None)

@st.cache_data(ttl=3600, show_spinner=False)
def sector_map() -> dict:
    """Mappa ticker → {sector, industry} da data/sector_map.json, rigenerabile
    con scripts/download_sectors_map.py --refresh (pattern dei CSV indici:
    file committato, mai scritto dal portale). Terzo livello quando Yahoo non
    espone settore/industria (mid cap europee, ADR)."""
    try:
        if not SECTOR_MAP_JSON.exists():
            return {}
        data = json.loads(SECTOR_MAP_JSON.read_text())
        return data.get("map", data) if isinstance(data, dict) else {}
    except Exception:
        return {}

def _info(ticker: str) -> dict:
    try:
        from core.data_engine import get_info
        info = get_info(ticker) or {}
    except Exception:
        info = {}
    if not info:
        try:
            info = yf.Ticker(ticker).info or {}
        except Exception:
            info = {}
    return info

@st.cache_data(ttl=86400, show_spinner=False)
def inquadra(ticker: str) -> tuple[str | None, str | None, str | None]:
    """(settore GICS, sotto-settore, tema) di un titolo. Live → mappa del repo
    → (None, None, None): 'non classificato' resta non classificato."""
    info = _info(ticker)
    out = classify(info.get("sector"), info.get("industry"))
    if any(out):
        return out
    entry = sector_map().get(ticker)
    if isinstance(entry, dict):
        return classify(entry.get("sector"), entry.get("industry"))
    return (None, None, None)

@st.cache_data(ttl=86400, show_spinner=False)
def sector_of(ticker: str) -> str | None:
    """Chiave GICS di un titolo (livello usato da punteggio, alert, Priorità)."""
    return inquadra(ticker)[0]

@st.cache_data(ttl=86400, show_spinner=False)
def sub_of(ticker: str) -> str | None:
    """Chiave di sotto-settore S&P Select Industry (lettura fine del trend)."""
    return inquadra(ticker)[1]

def valid_key(key: str | None) -> str | None:
    """Chiave utilizzabile: i campi salvati in watchlist/screening possono venire
    da un registro precedente (dopo una revisione della tassonomia). Una chiave
    sconosciuta non è un settore: si riclassifica il titolo."""
    return key if spec_of(key) else None

def of_registry(key: str | None) -> str:
    return livello_of(key or "")

def sector_label(key: str | None) -> str:
    spec = spec_of(key) if key else None
    return spec["label"] if spec else "—"

def genitore_label(key: str | None) -> str:
    """Etichetta del settore GICS genitore di un sotto-settore/tema."""
    return sector_label(parent(key or ""))

ARROW = {"in crescita": "↑", "in calo": "↓", "laterale": "→"}

def vento(key: str | None, rows: dict | None) -> str:
    """Unica fonte del giudizio 'vento': 'favore' | 'contro' | 'misto' | 'nd'.
    Le UI confrontano questa stringa, non lo stato interno di direzione: così
    il significato di 'settore in calo' è definito una volta sola."""
    r = (rows or {}).get(key or "")
    if not r or r.get("score") is None:
        return "nd"
    if r["dir"] == "in crescita":
        return "favore"
    if r["dir"] == "in calo":
        return "contro"
    return "misto"

def sector_cell(key: str | None, rows: dict) -> str:
    """Cella compatta per le tabelle: '🚀↑ 78' (stato, direzione, punteggio).
    '⚪ n/d' = dati non disponibili, NON 'mercato piatto'."""
    if not key:
        return "—"
    r = (rows or {}).get(key)
    if not r or r.get("score") is None:
        return "⚪ n/d"
    cell = f"{r['emoji']}{ARROW.get(r.get('dir'), '')} {round(r['score'])}"
    sp = r.get("spread")
    if sp is not None:
        cell += f" · Δ{sp:+.1f}" if abs(sp) < 2 else f" · Δ{sp:+.0f}"
    return cell


def note_for(key: str | None, rows: dict | None = None) -> str:
    """Una riga di contesto sul settore: lettura, non decisione."""
    if not key:
        return ""
    if rows is None:
        rows, _ = sector_rows()
    r = (rows or {}).get(key)
    if not r or r.get("score") is None:
        return (f"{sector_label(key)}: dati non disponibili (n/d)" if r is None
                else f"{r.get('label', key)}: dati non disponibili (n/d)")
    nome = r["label"]
    pref = {"settore": "Settore", "sotto-settore": "Sotto-settore",
            "tema": "Tema"}.get(r.get("livello", ""), "unità")
    txt = (f"{r['emoji']} {pref} {nome} {r['stato'].lower()} ({r['score']}/100)")
    if r.get("mom63") is not None:
        txt += f" · 3 mesi {r['mom63']:+.1f}%"
    if r.get("spread") is not None:
        txt += f" · Δ EW−CW 3m {r['spread']:+.1f} pt"
    if r.get("guida") and r["guida"] != "n/d":
        txt += f" · {r['guida']}"
    if r["dir"] == "in crescita":
        txt += " — vento a favore sul settore"
    elif r["dir"] == "in calo":
        txt += " — ⚠️ vento CONTRO: titolo candidato in settore in calo"
    else:
        txt += " — settore in fase mista/laterale"
    return txt

# ── Priorità (lettura gerarchica, mai regola di ingresso) ──
def bonus_sector(score: float | None) -> int:
    """±10 dal contesto di settore (50 = neutro)."""
    if score is None:
        return 0
    return int(round(np.clip((score - 50.0) / 5.0, -10, 10)))

def priorita(bottom: float | None, score: float | None) -> int | None:
    if bottom is None:
        return None
    return int(round(bottom + bonus_sector(score)))

def alert_sector_note(key: str | None, rows: dict | None = None) -> str:
    """Riga in più nei messaggi Telegram. Solo testo: non tocca chiavi di dedup,
    cooldown né day_lock."""
    if not key:
        return ""
    if rows is None:
        rows, _ = sector_rows()
    r = (rows or {}).get(key)
    if not r or r.get("score") is None:
        return ""
    lbl = r["label"]
    if r["dir"] == "in calo":
        return f"\n⚠️ settore {lbl} in calo ({r['score']}/100): ingresso contro-trend di settore"
    if r["dir"] == "in crescita" and r["stato"] in ("FORTE", "IN MIGLIORAMENTO"):
        return f"\n✅ settore {lbl} in crescita ({r['score']}/100): vento a favore"
    return ""

# ── Serie e tabelle per i grafici ──────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def sector_series(keys: tuple, window: int = 252) -> pd.DataFrame:
    """Columnne lunghe `window` sedute per i grafici: per ogni chiave la gamba
    capitalizzazione (se esiste) e quella a pesi uguali (se esiste), piu i due
    benchmark di mercato, piu `Δ · <label>` = rapporto EW/CW (base 100 all'inizio
    della finestra: sopra 100 = i pesi uguali stanno guadagnando sul CW).
    Chiavi senza una delle due gambe: la colonna mancante non viene creata, non
    viene inventata."""
    need = list(dict.fromkeys([BENCHMARK, BENCHMARK_EW]
                              + [t for k in keys for side in ("cw", "ew")
                                 for t in legs(k, side)]))
    try:
        closes = etf_closes(tuple(sorted(set(need))))
    except Exception:
        return pd.DataFrame()
    out = {}
    for k in keys:
        spec = spec_of(k)
        if not spec:
            continue
        lab = spec["label"]
        c = _close_column(closes, spec["cw"]) if spec.get("cw") else None
        e = _close_column(closes, spec["ew"]) if spec.get("ew") else None
        if c is not None:
            out[f"CW · {lab}"] = c
        if e is not None:
            out[f"EW · {lab}"] = e
        if c is not None and e is not None:
            out[f"Δ · {lab}"] = e / c
    for t, name in ((BENCHMARK, f"Mercato · {BENCHMARK}"),
                    (BENCHMARK_EW, f"Mercato EW · {BENCHMARK_EW}")):
        c = _close_column(closes, t)
        if c is not None:
            out[name] = c
    if not out:
        return pd.DataFrame()
    df = pd.DataFrame(out).sort_index().tail(window)
    return df.dropna(how="all").ffill()

@st.cache_data(ttl=3600, show_spinner=False)
def legs_detail(keys: tuple) -> pd.DataFrame:
    """Tabella numerica gamba-per-gamba: per ogni ETF dei registri momentum
    1/3/6 mesi, forza relativa 3m vs mercato, posizione su 52 settimane.
    E` il livello sotto cui non si scende restando nella tassonomia."""
    try:
        closes = etf_closes(tuple(etf_universe()))
        bench = _close_column(closes, BENCHMARK)
    except Exception:
        return pd.DataFrame()
    rows = []
    for k in keys:
        spec = spec_of(k)
        if not spec:
            continue
        for side in ("cw", "ew"):
            for t in _l(spec.get(side)):
                c = _close_column(closes, t)
                st = leg_stats(c if c is not None else pd.Series(dtype=float), bench)
                rows.append({"chiave": k, "label": spec["label"],
                             "livello": livello_of(k),
                             "gics": sector_label(spec.get("gics")),
                             "gamba": "capitalizzazione" if side == "cw" else "pesi uguali",
                             "etf": t, "mom21": st["mom21"], "mom63": st["mom63"],
                             "mom126": st["mom126"], "rs63": st["rs63"],
                             "pos52": st["pos52"], "sopra50": st["above50"]})
    return pd.DataFrame(rows)

def trend_table(rows: dict) -> pd.DataFrame:
    """La stessa cifra dei grafici in forma numerica. Le colonne CW/EW sono
    NOMINATE: una riga letta sulla gamba equal-weighted (perche` il gemello a
    capitalizzazione non esiste) lascia vuoti i campi CW, non zeppi."""
    rec = []
    for k, r in rows.items():
        rec.append({
            "key": k, "Settore": r.get("label", k),
            "Livello": r.get("livello", "n/d"),
            "GICS": sector_label(r.get("gics")),
            "Etichetta CW": r.get("cw") or "—", "Etichetta EW": r.get("ew") or "—",
            "Stato": f"{r.get('emoji', '⚪')} {r.get('stato', 'n/d')}",
            "Score": r.get("score"), "Dir": r.get("dir", "n/d"),
            "CW 1m": r.get("cw_mom21"), "CW 3m": r.get("cw_mom63"),
            "CW 6m": r.get("cw_mom126"),
            "EW 1m": r.get("ew_mom21"), "EW 3m": r.get("ew_mom63"),
            "EW 6m": r.get("ew_mom126"),
            "Δ 1m": r.get("d21"), "Δ 3m": r.get("d63"), "Δ 6m": r.get("d126"),
            "RS 3m": r.get("rs63"), "Consistenza": r.get("consistenza"),
            "Streak": r.get("streak"), "Range Δ": r.get("pos_ratio"),
            "Pos 52": r.get("pos52"), "Guida": r.get("guida", "n/d"),
            "Lettura": r.get("lettura", "n/d"),
            "Note": r.get("note") or "",
        })
    return pd.DataFrame(rec)

def groups_of(rows: dict) -> dict:
    """Raggruppamento standard: settore GICS -> sotto-settori/temi collegati
    (e` la mappa dei registri, non una famiglia inventata)."""
    out: dict[str, list] = {k: [] for k in SECTORS}
    for k, r in rows.items():
        g = r.get("gics")
        if g in out and k not in out[g]:
            out[g].append(k)
    return out

def indexed(closes: pd.DataFrame) -> pd.DataFrame:
    """Normalizza a 100 all'inizio del finestrino (per i rapporti moltiplica
    prima: indexed(ratio)*100 e` il rapporto indicizzato)."""
    first = closes.apply(lambda s: s.dropna().iloc[0] if s.dropna().size else np.nan)
    return closes / first * 100.0


def sub_note(key: str | None, rows: dict | None = None) -> str:
    """Riga di contesto sul sotto-settore S&P Select Industry (livello fine).
    Rows=_None: usa la cache dei sotto-settori, non riscarica nulla."""
    if not key:
        return ""
    if rows is None:
        rows, _ = sub_rows()
    txt = note_for(key, rows)
    if not txt:
        return ""
    r = (rows or {}).get(key) or {}
    if r.get("gics"):
        txt += f" — dentro il settore {sector_label(r['gics'])}"
    if r.get("riferimento") == "ew" and r.get("cw") is None:
        txt += " (nessun benchmark a capitalizzazione su questo perimetro: " \
               "il Δ non è calcolabile)"
    return txt


def sub_cell(key: str | None, rows: dict) -> str:
    return sector_cell(key, rows)


def rotation_digest(snap: dict | None) -> str:
    """Riassunto testuale della rotazione di chiusura: forti / deboli / Δ EW−CW.
    Testo, non segnale: da allegare a una notifica, non genera invii propri."""
    rows = (snap or {}).get("rows") or {}
    g = [r for r in rows.values() if r.get("livello") == "settore"
         and r.get("score") is not None]
    if not g:
        return ""
    g.sort(key=lambda r: -r["score"])
    dq = [r for r in rows.values() if r.get("livello") == "sotto-settore"
          and r.get("d63") is not None]
    dq.sort(key=lambda r: -r["d63"])
    riga = lambda r: f"{r['emoji']} {r['label']} {r['score']:.0f} ({r['dir']})"
    txt = [f"🏭 ROTAZIONE SETTORI — chiusura {snap.get('asof') or 'n/d'}",
           "forti: " + " · ".join(riga(r) for r in g[:4]),
           "deboli: " + " · ".join(riga(r) for r in g[-4:][::-1])]
    if dq:
        txt.append("Δ EW−CW 3m: " + " · ".join(
            f"{r['label']} {r['d63']:+.1f}" for r in (dq[:3] + dq[-3:][::-1])))
    b = (snap or {}).get("bench_mom63")
    if b is not None:
        txt.append(f"mercato {snap.get('benchmark','SPY')} 3m {b:+.1f}%")
    return "\n".join(txt)


def digest_should_notify(environ: dict | None = None) -> bool:
    """Il digest serale parte SOLO se lo chiedi esplicitamente: il job cron non
    passa questo flag, il workflow manuale sì (vedi settori.yml)."""
    import os
    e = environ if environ is not None else os.environ
    return str(e.get("SETTORI_NOTIFICA", "")).strip().lower() in ("1", "true", "si", "sì")
