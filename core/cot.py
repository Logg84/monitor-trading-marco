"""
COT: parsing CFTC robusto con RILEVAMENTO AUTOMATICO COLONNE
(Producer / Managed-Spec / Swap × Long/Short) per Legacy, Disaggregated, TFF.
Mancante = None (mai zeri finti). Storage locale + publish GitHub opzionale
se GITHUB_TOKEN/GITHUB_REPO nei secrets. Reset per storico avvelenato.
"""
from __future__ import annotations

import datetime
import io
import json
import re
import zipfile
import base64
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import streamlit as st

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
COT_DIR = DATA_DIR / "cot"
COT_JSON = COT_DIR / "cot_data.json"
DIAG_JSON = COT_DIR / "last_diag.json"

WINDOW = 104
MINW = 52

try:
    GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN")
    GITHUB_REPO = st.secrets.get("GITHUB_REPO")
except Exception:
    GITHUB_TOKEN, GITHUB_REPO = None, None

YF_COMM = {
    "GOLD": "GC=F", "SILVER": "SI=F", "COPPER": "HG=F", "PLATINUM": "PL=F",
    "WTI": "CL=F", "BRENT": "BZ=F", "NG": "NG=F",
    "CORN": "ZC=F", "WHEAT": "ZW=F", "SOYBEANS": "ZS=F",
    "SOYBEAN_OIL": "ZL=F", "SOYBEAN_MEAL": "ZM=F",
    "COTTON": "CT=F", "COFFEE": "KC=F", "SUGAR11": "SB=F", "COCOA": "CC=F",
    "OJ": "OJ=F", "LUMBER": "LBS=F", "LIVE_CATTLE": "LE=F",
    "LEAN_HOGS": "HE=F",
}

CFTC_TO_FX = {
    "EURO FX": "EUR", "BRITISH POUND": "GBP", "JAPANESE YEN": "JPY",
    "AUSTRALIAN DOLLAR": "AUD", "CANADIAN DOLLAR": "CAD",
    "SWISS FRANC": "CHF", "NEW ZEALAND DOLLAR": "NZD",
    # Il nome reale nel campo Market_and_Exchange_Names di CFTC è
    # "USD INDEX - ICE FUTURES U.S.", non "US DOLLAR INDEX": con la
    # stringa sbagliata _mask_mercato non trovava mai nessuna riga
    # (né match esatto né come prefisso), quindi il dollaro veniva
    # silenziosamente saltato in ogni elaborazione, senza errore visibile.
    "USD INDEX": "USD",
}

CFTC_TO_COMM = {
    "WHEAT": "WHEAT", "CORN": "CORN", "OATS": "OATS", "SOYBEANS": "SOYBEANS",
    "SOYBEAN OIL": "SOYBEAN_OIL", "SOYBEAN MEAL": "SOYBEAN_MEAL",
    "COTTON": "COTTON", "ORANGE JUICE": "OJ", "ROUGH RICE": "ROUGH_RICE",
    "LIVE CATTLE": "LIVE_CATTLE", "LEAN HOGS": "LEAN_HOGS", "LUMBER": "LUMBER",
    "GOLD": "GOLD", "SILVER": "SILVER", "COPPER": "COPPER",
    "NATURAL GAS": "NG", "CRUDE OIL": "WTI", "BRENT CRUDE OIL": "BRENT",
}

COMM_NAMES = {
    "WHEAT": "🌾 Frumento", "CORN": "🌽 Mais", "OATS": "🥣 Avena",
    "SOYBEANS": "🫘 Soia", "SOYBEAN_OIL": "🫗 Olio di soia",
    "SOYBEAN_MEAL": "🥜 Farina di soia", "COTTON": "🧶 Cotone",
    "OJ": "🍊 Succo d'arancia", "ROUGH_RICE": "🍚 Riso",
    "LIVE_CATTLE": "🐂 Bovini vivi", "LEAN_HOGS": "🐖 Suini magri",
    "LUMBER": "🪵 Legname", "GOLD": "🥇 Oro", "SILVER": "🥈 Argento",
    "COPPER": "🟠 Rame", "NG": "🔥 Gas Naturale", "WTI": "🛢️ Petrolio WTI",
    "BRENT": "⛽ Brent",
}

FX_ORDER = ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD", "USD"]
COMM_ORDER = ["GOLD", "SILVER", "COPPER", "WTI", "BRENT", "NG",
              "CORN", "WHEAT", "SOYBEANS", "SOYBEAN_OIL", "SOYBEAN_MEAL",
              "OATS", "ROUGH_RICE", "COTTON", "OJ", "LUMBER",
              "LIVE_CATTLE", "LEAN_HOGS"]

# ════════════════════════════════════════════════════════════
# RILEVAMENTO AUTOMATICO COLONNE (indipendente dal formato CFTC)
# ════════════════════════════════════════════════════════════
def _norm_col(c) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(c).lower())

def _cat_of(h: str) -> str | None:
    if "spread" in h or "openinterest" in h:
        return None
    if "swap" in h:
        return "swap"
    if "noncomm" in h or "managed" in h or "money" in h or "leveraged" in h:
        return "mm"
    if "prod" in h or "commercial" in h or "merchant" in h:
        return "prod"
    return None

def _ls_of(h: str) -> str | None:
    if "long" in h and "short" not in h:
        return "L"
    if "short" in h:
        return "S"
    return None

def _colmap(df: pd.DataFrame) -> dict:
    """{categoria: {"L": col, "S": col}}"""
    m = {}
    for c in df.columns:
        h = _norm_col(c)
        cat, ls = _cat_of(h), _ls_of(h)
        if cat and ls:
            m.setdefault(cat, {}).setdefault(ls, c)
    return m

# ════════════════════════════════════════════════════════════
# LETTURA ZIP CFTC (Annual → 0 → qualsiasi foglio valido)
# ════════════════════════════════════════════════════════════
def _leggi_sheet_cftc(inner: bytes) -> pd.DataFrame:
    for eng in ("xlrd", None, "openpyxl"):
        try:
            df = pd.read_excel(io.BytesIO(inner), sheet_name="Annual", engine=eng)
            if "Market_and_Exchange_Names" in df.columns:
                return df
        except Exception:
            pass
    for eng in ("xlrd", None, "openpyxl"):
        try:
            df = pd.read_excel(io.BytesIO(inner), sheet_name=0, engine=eng)
            if "Market_and_Exchange_Names" in df.columns:
                return df
        except Exception:
            pass
    for eng in ("xlrd", None, "openpyxl"):
        try:
            sheets = pd.read_excel(io.BytesIO(inner), sheet_name=None, engine=eng)
            for name, df in sheets.items():
                if isinstance(df, pd.DataFrame) and "Market_and_Exchange_Names" in df.columns:
                    return df
        except Exception:
            continue
    raise RuntimeError("Nessun foglio con Market_and_Exchange_Names trovato nello zip")

def leggi_zip_bytes(content: bytes) -> pd.DataFrame:
    zf = zipfile.ZipFile(io.BytesIO(content))
    nomi = [n for n in zf.namelist() if n.lower().endswith((".xls", ".xlsx"))]
    if not nomi:
        raise RuntimeError("Nessun file .xls dentro lo zip")
    return _leggi_sheet_cftc(zf.read(nomi[0]))

def _mask_mercato(df: pd.DataFrame, nome_cftc: str):
    col = df["Market_and_Exchange_Names"].astype(str).str.upper().str.strip()
    t = nome_cftc.upper().strip()
    m = (col == t)
    if not m.any():
        m = col.str.startswith(t)
    if nome_cftc == "CRUDE OIL":
        m = m & ~col.str.contains("BRENT")
    return m

def _rows_ordinate(df: pd.DataFrame, nome_cftc: str) -> pd.DataFrame:
    if "Market_and_Exchange_Names" not in df.columns:
        return pd.DataFrame()
    rows = df[_mask_mercato(df, nome_cftc)].copy()
    dcol = next((c for c in df.columns
                 if _norm_col(c).startswith("reportdate")), None)
    if dcol is None:
        return pd.DataFrame()
    rows["_rd"] = pd.to_datetime(rows[dcol], errors="coerce")
    return rows.dropna(subset=["_rd"]).sort_values("_rd")

def _num(row, col):
    if col is None:
        return None
    v = pd.to_numeric(row.get(col), errors="coerce")
    return float(v) if pd.notna(v) else None

def processa_dfs(df: pd.DataFrame) -> tuple[dict, dict]:
    cm = _colmap(df)
    fx, comm = {}, {}

    mm_cols = cm.get("mm", {})
    if mm_cols.get("L") and mm_cols.get("S"):
        for nome_cftc, simbolo in CFTC_TO_FX.items():
            rows = _rows_ordinate(df, nome_cftc)
            if rows.empty:
                continue
            serie = []
            for _, row in rows.iterrows():
                l = _num(row, mm_cols["L"])
                s = _num(row, mm_cols["S"])
                if l is None or s is None:
                    continue
                serie.append({"t": int(row["_rd"].timestamp() * 1000),
                              "nc": l - s})
            if serie:
                fx[simbolo] = serie

    for nome_cftc, simbolo in CFTC_TO_COMM.items():
        rows = _rows_ordinate(df, nome_cftc)
        if rows.empty:
            continue
        pc, mc, sc = cm.get("prod", {}), cm.get("mm", {}), cm.get("swap", {})
        serie = []
        for _, row in rows.iterrows():
            pl, ps = _num(row, pc.get("L")), _num(row, pc.get("S"))
            ml, ms = _num(row, mc.get("L")), _num(row, mc.get("S"))
            sl, ss = _num(row, sc.get("L")), _num(row, sc.get("S"))
            prod = (pl - ps) if (pl is not None and ps is not None) else None
            mm = (ml - ms) if (ml is not None and ms is not None) else None
            swap = (sl - ss) if (sl is not None and ss is not None) else None
            if prod is None and mm is None and swap is None:
                continue
            serie.append({"t": int(row["_rd"].timestamp() * 1000),
                          "prod": prod, "mm": mm, "swap": swap})
        if serie:
            comm[simbolo] = serie
    return fx, comm

def _rich(x: dict, keys) -> int:
    return sum(1 for k in keys if x.get(k) is not None)

def _acc(acc: dict, new: dict, keys) -> dict:
    """Accumula serie per mercato/settimana: vince la riga più ricca."""
    out = {k: {x["t"]: x for x in v} for k, v in acc.items()}
    for sym, serie in new.items():
        bucket = out.setdefault(sym, {})
        for x in serie:
            cur = bucket.get(x["t"])
            if cur is None or _rich(x, keys) > _rich(cur, keys):
                bucket[x["t"]] = x
    return {sym: [bucket[t] for t in sorted(bucket)] for sym, bucket in out.items()}

def merge_con_esistente(existing_fx, existing_comm, new_fx, new_comm):
    def _merge(old, new):
        out = {k: list(v) for k, v in (old or {}).items()}
        for k, v in (new or {}).items():
            if k in out and out[k]:
                last_t = max(x["t"] for x in out[k])
                out[k] += [x for x in v if x["t"] > last_t]
            else:
                out[k] = list(v)
        return out
    return _merge(existing_fx, new_fx), _merge(existing_comm, new_comm)

# ════════════════════════════════════════════════════════════
# DIAGNOSTICA
# ════════════════════════════════════════════════════════════
def _diag_zip(content: bytes, fname: str) -> dict:
    info = {"file": fname, "n_xls": 0, "xls_in_zip": [], "shape": None,
            "columns": [], "colmap": {}, "date_min": None, "date_max": None,
            "markets_sample": [], "fx_matched": 0, "comm_matched": 0}
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
        nomi = [n for n in zf.namelist() if n.lower().endswith((".xls", ".xlsx"))]
        info["n_xls"] = len(nomi)
        info["xls_in_zip"] = nomi[:8] + ([f"…(+{len(nomi) - 8})"] if len(nomi) > 8 else [])
        if not nomi:
            return info
        df = _leggi_sheet_cftc(zf.read(nomi[0]))
        info["shape"] = list(df.shape)
        info["columns"] = [str(c) for c in df.columns][:30]
        info["colmap"] = {cat: {ls: str(c) for ls, c in v.items()}
                          for cat, v in _colmap(df).items()}
        dcol = next((c for c in df.columns
                     if _norm_col(c).startswith("reportdate")), None)
        if dcol:
            d = pd.to_datetime(df[dcol], errors="coerce")
            info["date_min"] = str(d.min())[:10]
            info["date_max"] = str(d.max())[:10]
        if "Market_and_Exchange_Names" in df.columns:
            mk = [str(x).upper().strip() for x in df["Market_and_Exchange_Names"].dropna().unique()]
            info["markets_sample"] = mk[:8]
            info["fx_matched"] = sum(1 for n in CFTC_TO_FX
                                     if any(u == n or u.startswith(n) for u in mk))
            info["comm_matched"] = sum(1 for n in CFTC_TO_COMM
                                       if any(u == n or u.startswith(n) for u in mk))
    except Exception as e:
        info["error"] = str(e)
    return info

def load_diag() -> list | None:
    if DIAG_JSON.exists():
        try:
            return json.loads(DIAG_JSON.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None

# ════════════════════════════════════════════════════════════
# STORAGE + PUBLISH GITHUB (opzionale, come vecchio codice)
# ════════════════════════════════════════════════════════════
def load_cot_data() -> dict | None:
    if COT_JSON.exists():
        try:
            return json.loads(COT_JSON.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None

def _build_payload(fx: dict, comm: dict) -> dict:
    ultima = 0
    for v in list(fx.values()) + list(comm.values()):
        if v:
            ultima = max(ultima, v[-1]["t"])
    data_str = (datetime.datetime.fromtimestamp(ultima / 1000, datetime.timezone.utc)
                .strftime("%Y-%m-%d")) if ultima else ""
    max_sett = max((len(v) for v in list(fx.values()) + list(comm.values())), default=0)
    return {
        "meta": {
            "date": data_str,
            "weeks": max_sett,
            "src": "PORTALE·upload",
            "gen": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "fx_n": len(fx), "cm_n": len(comm),
            "rec": sum(len(v) for v in list(fx.values()) + list(comm.values())),
        },
        "fx": {k: fx[k] for k in FX_ORDER if k in fx},
        "comm": {k: comm[k] for k in COMM_ORDER if k in comm},
        "comm_name": COMM_NAMES,
        "fx_order": [k for k in FX_ORDER if k in fx],
        "comm_order": [k for k in COMM_ORDER if k in comm],
    }

def salva_payload(fx: dict, comm: dict) -> dict:
    COT_DIR.mkdir(parents=True, exist_ok=True)
    payload = _build_payload(fx, comm)
    COT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if GITHUB_TOKEN and GITHUB_REPO:
        try:
            # Allineato al percorso locale (data/cot/cot_data.json): prima
            # scriveva su "cot_data.json" in root, creando un duplicato
            # disallineato mai riletto da nessuna parte del codice.
            url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/data/cot/cot_data.json"
            headers = {"Authorization": f"token {GITHUB_TOKEN}",
                       "Accept": "application/vnd.github.v3+json"}
            r = requests.get(url, headers=headers, timeout=30)
            sha = r.json().get("sha") if r.status_code == 200 else None
            put = {
                "message": f"chore(cot): aggiornamento manuale {datetime.date.today().isoformat()}",
                "content": base64.b64encode(json.dumps(payload, indent=2).encode()).decode(),
                "branch": "main",
            }
            if sha:
                put["sha"] = sha
            requests.put(url, headers=headers, json=put, timeout=30)
        except Exception as e:
            print("Publish GitHub non riuscito (resto locale):", e)
    return payload

def processa_e_salva(zip_list: list[tuple[str, bytes]], reset: bool = False) -> dict:
    COT_DIR.mkdir(parents=True, exist_ok=True)
    diag = [_diag_zip(b, n) for n, b in zip_list]
    DIAG_JSON.write_text(json.dumps(diag, indent=2), encoding="utf-8")

    fx_acc, comm_acc = {}, {}
    for _, b in zip_list:
        df = leggi_zip_bytes(b)
        f_i, c_i = processa_dfs(df)
        fx_acc = _acc(fx_acc, f_i, ["nc"])
        comm_acc = _acc(comm_acc, c_i, ["prod", "mm", "swap"])

    if not fx_acc and not comm_acc:
        raise RuntimeError("Nessun mercato riconosciuto nei zip caricati. "
                           "Apri data/cot/last_diag.json per vedere colonne reali.")
    # reset=True → ignora lo storico (es. avvelenato da elaborazioni sbagliate)
    old = {} if reset else (load_cot_data() or {})
    fx, comm = merge_con_esistente(old.get("fx", {}), old.get("comm", {}),
                                   fx_acc, comm_acc)
    return salva_payload(fx, comm)

# ════════════════════════════════════════════════════════════
# ANALYTICS (None-safe)
# ════════════════════════════════════════════════════════════
def series(a: list, k: str) -> list:
    return [x[k] for x in a[-WINDOW:] if x.get(k) is not None]

def percentile(a: list, v: float) -> float:
    if not a:
        return 50.0
    s = sorted(a)
    b = 0
    for x in s:
        if x < v:
            b += 1
        else:
            break
    return b / len(s) * 100

def zscore(a: list, w: int = 52) -> float:
    r = a[-w:]
    if len(r) < 5:
        return 0.0
    m = sum(r) / len(r)
    sd = (sum((x - m) ** 2 for x in r) / len(r)) ** .5
    return 0.0 if sd == 0 else (a[-1] - m) / sd

def deriv(a: list, w: int = 2) -> float:
    if len(a) < w + 1:
        return 0.0
    r = a[-w - 1:]
    return r[-1] - r[0]

def reversing(a: list, w: int = 2) -> bool:
    if len(a) < w + 1:
        return False
    r = a[-w - 1:]
    d = [r[i] - r[i - 1] for i in range(1, len(r))]
    return all(x > 0 for x in d) or all(x < 0 for x in d)

def comm_state(sym: str, comm: dict) -> dict:
    """REGOLA HOT ALLARGATA: Producer estremo (pP<10 o pP>90) => hot anche
    senza Managed estremo."""
    arr = comm.get(sym) or []
    pA, mA, sA = series(arr, "prod"), series(arr, "mm"), series(arr, "swap")
    if len(arr) < MINW or len(pA) < 10 or len(mA) < 10:
        return {"key": "flat", "tone": "muted", "pP": 50, "pM": 50, "pS": 50,
                "dP": 0, "dM": 0, "revP": False}
    pP, pM = percentile(pA, pA[-1]), percentile(mA, mA[-1])
    pS = percentile(sA, sA[-1]) if sA else 50.0
    dP, dM, revP = deriv(pA), deriv(mA), reversing(pA)
    if pP < 20 and pM > 65:
        key, tone = "bull", "green"
    elif pP > 80 and pM < 35:
        key, tone = "bear", "red"
    elif (pM > 85 or pM < 15) and not revP:
        key, tone = "watch", "yellow"
    elif abs(dM) > abs(dP) * 1.2 and 15 <= pM <= 85:
        key, tone = "trend", "ice"
    elif (pP < 10 or pP > 90):
        key, tone = "hot_producer", "yellow"
    else:
        key, tone = "flat", "muted"
    return {"key": key, "tone": tone, "pP": pP, "pM": pM, "pS": pS,
            "dP": dP, "dM": dM, "revP": revP}

# ════════════════════════════════════════════════════════════
# ANALISI PER COPPIA FOREX (non per singola valuta)
# ════════════════════════════════════════════════════════════
# Il dato COT per il forex è per-valuta (net positioning speculativo
# contro USD, o l'indice USD stesso), ma una coppia è per definizione
# un confronto tra due gambe. Guardare EUR da sola e ignorare cosa fa
# USD nello stesso momento significa perdere il caso più informativo:
# quando entrambe le gambe sono estreme nella STESSA direzione, i
# segnali si annullano a vicenda invece di sommarsi.
#
# "quote_is_usd_index": True per le coppie dirette contro USD (la
# valuta base è quotata sui futures CME/ICE direttamente contro USD,
# quindi la "gamba quote" è l'USD Index). False per i cross (entrambe
# le gambe sono valute non-USD, es. EURGBP, EURJPY).
FX_PAIRS = {
    "EURUSD": ("EUR", "USD"), "GBPUSD": ("GBP", "USD"),
    "AUDUSD": ("AUD", "USD"), "NZDUSD": ("NZD", "USD"),
    "USDJPY": ("USD", "JPY"), "USDCHF": ("USD", "CHF"),
    "USDCAD": ("USD", "CAD"),
    # Cross: nessuna gamba è USD, la divergenza si calcola direttamente
    # tra le due valute non-USD, senza passare dall'indice.
    "EURGBP": ("EUR", "GBP"), "EURJPY": ("EUR", "JPY"),
    "GBPJPY": ("GBP", "JPY"), "AUDJPY": ("AUD", "JPY"),
    "EURCHF": ("EUR", "CHF"), "EURAUD": ("EUR", "AUD"),
}

def _fx_leg(sym: str, fx: dict) -> dict:
    """Percentile, derivata e accenno di inversione del net positioning
    di una singola valuta."""
    arr = fx.get(sym) or []
    v = series(arr, "nc")
    if len(arr) < MINW or len(v) < 10:
        return {"p": 50.0, "d": 0.0, "n": len(v), "turn": None}
    p = percentile(v, v[-1])
    d_ultimo = deriv(v, w=1)   # variazione ultima settimana
    d_trend = deriv(v, w=4)    # variazione ultime 4 settimane (il trend che ha portato all'estremo)
    # Accenno di inversione: la gamba è al proprio estremo, il trend a
    # 4 settimane è ancora nella direzione che l'ha portata lì, ma
    # l'ULTIMO tick va nella direzione opposta. Un solo tick non fa un
    # nuovo trend — per questo resta un "avviso", non un cambio di
    # classificazione: la userà chi legge per pesare la convinzione,
    # non per ribaltare il segnale.
    turn = None
    if p > 80 and d_trend > 0 and d_ultimo < 0:
        turn = "down"   # long estremo che inizia a cedere
    elif p < 20 and d_trend < 0 and d_ultimo > 0:
        turn = "up"     # short estremo che inizia a recuperare
    return {"p": p, "d": deriv(v), "n": len(v), "turn": turn}

def fx_pair_state(pair: str, fx: dict) -> dict | None:
    """
    Stato COT per una coppia forex, basato sulla DIVERGENZA tra le due
    gambe — non sul percentile isolato di una sola valuta.

    key:
      "bull_aligned"  — base in accumulo estremo (pB<20) mentre la quote
                         non lo è (pQ>35): le due gambe puntano nella
                         stessa direzione per la coppia, segnale pulito.
      "bear_aligned"  — speculare, ribassista.
      "crowded"       — entrambe le gambe estreme nella STESSA direzione
                         (es. EUR long estremo E USD long estremo): i
                         segnali si annullano, il posizionamento non dice
                         nulla sulla direzione della COPPIA anche se dice
                         molto sulle due valute prese singolarmente.
      "watch"         — solo una gamba è estrema, l'altra è neutra:
                         segnale parziale, da monitorare non da seguire.
      "flat"          — nessuna gamba in zona estrema, dati insufficienti.

    "avviso_inversione": non None se una delle due gambe che alimentano
    il segnale mostra un accenno (un solo tick) di inversione rispetto
    al trend che l'ha portata all'estremo — riduce la convinzione sul
    segnale senza cancellarlo.
    """
    if pair not in FX_PAIRS:
        return None
    base_sym, quote_sym = FX_PAIRS[pair]
    base = _fx_leg(base_sym, fx)
    quote = _fx_leg(quote_sym, fx)
    if base["n"] < 10 or quote["n"] < 10:
        return {"key": "flat", "tone": "muted", "pBase": 50, "pQuote": 50,
                "divergenza": 0, "base": base_sym, "quote": quote_sym,
                "avviso_inversione": None}

    pB, pQ = base["p"], quote["p"]
    # Divergenza diretta: quanto la base è più "comprata" della quote sul
    # proprio storico. Va da -100 (quote massimamente più comprata) a
    # +100 (base massimamente più comprata).
    divergenza = (pB - pQ)

    base_estrema_long = pB > 80
    base_estrema_short = pB < 20
    quote_estrema_long = pQ > 80
    quote_estrema_short = pQ < 20

    if base_estrema_long and quote_estrema_long:
        key, tone = "crowded", "ice"
    elif base_estrema_short and quote_estrema_short:
        key, tone = "crowded", "ice"
    elif base_estrema_long and (quote_estrema_short or 35 <= pQ <= 65):
        key, tone = "bull_aligned", "green"
    elif base_estrema_short and (quote_estrema_long or 35 <= pQ <= 65):
        key, tone = "bear_aligned", "red"
    elif base_estrema_long or base_estrema_short or quote_estrema_long or quote_estrema_short:
        key, tone = "watch", "yellow"
    else:
        key, tone = "flat", "muted"

    # L'avviso guarda solo la/le gamba/e effettivamente estrema/e che
    # determina/determinano il segnale (non una gamba neutra in mezzo).
    avviso = None
    if key in ("bull_aligned", "bear_aligned", "crowded", "watch"):
        note = []
        if base_estrema_long and base["turn"] == "down":
            note.append(f"{base_sym} long estremo in possibile cedimento")
        elif base_estrema_short and base["turn"] == "up":
            note.append(f"{base_sym} short estremo in possibile recupero")
        if quote_estrema_long and quote["turn"] == "down":
            note.append(f"{quote_sym} long estremo in possibile cedimento")
        elif quote_estrema_short and quote["turn"] == "up":
            note.append(f"{quote_sym} short estremo in possibile recupero")
        if note:
            avviso = "; ".join(note)

    return {
        "key": key, "tone": tone,
        "pBase": pB, "pQuote": pQ, "divergenza": divergenza,
        "dBase": base["d"], "dQuote": quote["d"],
        "base": base_sym, "quote": quote_sym,
        "avviso_inversione": avviso,
    }

def fx_pairs_ranked(fx: dict) -> list[dict]:
    """Tutte le coppie definite, ordinate per intensità di divergenza
    assoluta (le più 'sbilanciate' — quindi potenzialmente le più
    interessanti — in cima). Le 'crowded' vengono segnalate ma non sono
    per forza in cima, dato che il loro segnale direzionale è nullo per
    costruzione anche se entrambe le gambe sono estreme.
    NOTA: l'ordinamento resta per divergenza assoluta anche in presenza
    di "avviso_inversione" — l'avviso è un fattore di convinzione da
    mostrare, non un motivo per escludere o riordinare la coppia: un
    solo tick di inversione non giustifica un cambio di ranking."""
    out = []
    for pair in FX_PAIRS:
        st_ = fx_pair_state(pair, fx)
        if st_ and st_["key"] != "flat":
            out.append({"pair": pair, **st_})
    out.sort(key=lambda x: abs(x["divergenza"]), reverse=True)
    return out

def regime_scores(payload: dict | None) -> dict | None:
    """Score contrarian aggregati per la Bussola (attori COT)."""
    if not payload:
        return None
    pMs, pPs = [], []
    for sym in payload.get("comm_order", []):
        st_ = comm_state(sym, payload.get("comm", {}))
        if st_["key"] == "flat" and st_["pP"] == 50 and st_["pM"] == 50:
            continue
        pMs.append(st_["pM"])
        pPs.append(st_["pP"])
    for sym in payload.get("fx_order", []):
        a = payload["fx"].get(sym) or []
        if len(a) >= MINW:
            v = series(a, "nc")
            if v:
                pMs.append(percentile(v, v[-1]))
    if not pMs and not pPs:
        return None
    pM_avg = float(np.mean(pMs)) if pMs else 50.0
    pP_avg = float(np.mean(pPs)) if pPs else 50.0
    extreme = any(p <= 10 or p >= 90 for p in pPs)
    return {
        "managed_money": float(np.clip((50 - pM_avg) * 2, -100, 100)),
        "producers": float(np.clip((50 - pP_avg) * 2, -100, 100)),
        "managed_money_detail": f"percentile medio MM/spec {pM_avg:.0f}°",
        "producers_detail": f"percentile medio producer {pP_avg:.0f}°",
        "extreme_producer": extreme,
    }
