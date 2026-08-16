"""
cot_build.py – Scarica i dati COT dal CFTC e genera cot_data.json
Formato compatibile con pages/4_COT.py
Da eseguire in locale o via GitHub Actions una volta a settimana.

FIX 2026-08:
- Anno dinamico (corrente + precedente) => storico >= 104 settimane
- Download via requests con User-Agent (il CFTC rifiuta richieste senza UA)
- Lettura zip robusta (estrazione .xls interna, engine openpyxl/xlrd in fallback)
"""

import os
import io
import json
import zipfile
import datetime
import time
import requests
import pandas as pd
import numpy as np

# ===================== CONFIGURAZIONE =====================
OUTPUT_JSON = "cot_data.json"
OUTPUT_HTML = "cot_report.html"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}

# Mappa nomi CFTC → simboli usati in 4_COT.py
CFTC_TO_FX = {
    "EURO FX": "EUR",
    "BRITISH POUND": "GBP",
    "JAPANESE YEN": "JPY",
    "AUSTRALIAN DOLLAR": "AUD",
    "CANADIAN DOLLAR": "CAD",
    "SWISS FRANC": "CHF",
    "NEW ZEALAND DOLLAR": "NZD",
    "US DOLLAR INDEX": "USD",
}

CFTC_TO_COMM = {
    "WHEAT": "WHEAT",
    "CORN": "CORN",
    "OATS": "OATS",
    "SOYBEANS": "SOYBEANS",
    "SOYBEAN OIL": "SOYBEAN_OIL",
    "SOYBEAN MEAL": "SOYBEAN_MEAL",
    "COTTON": "COTTON",
    "ORANGE JUICE": "OJ",
    "ROUGH RICE": "ROUGH_RICE",
    "LIVE CATTLE": "LIVE_CATTLE",
    "LEAN HOGS": "LEAN_HOGS",
    "LUMBER": "LUMBER",
    "GOLD": "GOLD",
    "SILVER": "SILVER",
    "COPPER": "COPPER",
    "NATURAL GAS": "NG",
    "CRUDE OIL": "WTI",
    "BRENT CRUDE OIL": "BRENT",
}

# Nomi leggibili per il select nella pagina COT
COMM_NAMES = {
    "WHEAT": "🌾 Frumento", "CORN": "🌽 Mais", "OATS": "🥣 Avena",
    "SOYBEANS": "🫘 Soia", "SOYBEAN_OIL": "🫗 Olio di soia", "SOYBEAN_MEAL": "🥜 Farina di soia",
    "COTTON": "🧶 Cotone", "OJ": "🍊 Succo d'arancia", "ROUGH_RICE": "🍚 Riso",
    "LIVE_CATTLE": "🐂 Bovini vivi", "LEAN_HOGS": "🐖 Suini magri", "LUMBER": "🪵 Legname",
    "GOLD": "🥇 Oro", "SILVER": "🥈 Argento", "COPPER": "🟠 Rame",
    "NG": "🔥 Gas Naturale", "WTI": "🛢️ Petrolio WTI", "BRENT": "⛽ Brent",
}


def _read_annual(inner_bytes: bytes) -> pd.DataFrame:
    """Legge il foglio 'Annual' provando più engine (xlsx vs xls BIFF)."""
    errs = []
    for eng in (None, "openpyxl", "xlrd"):
        try:
            return pd.read_excel(io.BytesIO(inner_bytes), sheet_name="Annual", engine=eng)
        except Exception as e:
            errs.append(f"{eng or 'auto'}: {e}")
    raise RuntimeError("Lettura Annual fallita -> " + " | ".join(errs))


def _leggi_anno(anno: int) -> pd.DataFrame:
    url = f"https://www.cftc.gov/files/dea/history/fut_fin_xls_{anno}.zip"
    print(f"📡 Download {url} ...")
    r = requests.get(url, headers=UA, timeout=180)
    r.raise_for_status()
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    nomi = [n for n in zf.namelist() if n.lower().endswith((".xls", ".xlsx"))]
    if not nomi:
        raise RuntimeError(f"Nessun file .xls dentro lo zip {anno}")
    df = _read_annual(zf.read(nomi[0]))
    print(f"✅ Anno {anno}: {len(df)} righe")
    return df


def scarica_cot() -> pd.DataFrame:
    """Scarica anno corrente + precedente e li unisce (storico >= 104 settimane)."""
    anno = datetime.date.today().year
    dfs = []
    for y in (anno, anno - 1):
        try:
            dfs.append(_leggi_anno(y))
        except Exception as e:
            print(f"⚠️ Anno {y} fallito: {e}")
        time.sleep(1.0)
    if not dfs:
        print("❌ Nessun anno scaricato.")
        return pd.DataFrame()
    df = pd.concat(dfs, ignore_index=True)
    df = df.drop_duplicates(subset=["Market_and_Exchange_Names", "Report_Date_as_MM_DD_YYYY"])
    print(f"✅ Storico unito: {len(df)} righe ({anno} + {anno - 1}).")
    return df


def _rows_ordinate(df: pd.DataFrame, nome_cftc: str) -> pd.DataFrame:
    mask = df["Market_and_Exchange_Names"].str.upper().str.strip() == nome_cftc.upper().strip()
    rows = df[mask].copy()
    rows["_rd"] = pd.to_datetime(rows["Report_Date_as_MM_DD_YYYY"], errors="coerce")
    return rows.dropna(subset=["_rd"]).sort_values("_rd")


def processa_forex(df: pd.DataFrame) -> dict:
    """Estrae le serie storiche Forex (net long non-commercial)."""
    fx_data = {}
    for nome_cftc, simbolo in CFTC_TO_FX.items():
        rows = _rows_ordinate(df, nome_cftc)
        if rows.empty:
            print(f"⚠️ Forex {simbolo} non trovato.")
            continue
        serie = []
        for _, row in rows.iterrows():
            t = int(row["_rd"].timestamp() * 1000)
            nc = row.get("NonComm_Positions_Long_All", 0) - row.get("NonComm_Positions_Short_All", 0)
            serie.append({"t": t, "nc": float(nc)})
        if serie:
            fx_data[simbolo] = serie
            print(f"✅ Forex {simbolo}: {len(serie)} settimane")
    return fx_data


def processa_commodities(df: pd.DataFrame) -> dict:
    """Estrae le serie storiche Commodities (Producer/Merchant, Managed Money, Swap Dealer)."""
    comm_data = {}
    for nome_cftc, simbolo in CFTC_TO_COMM.items():
        rows = _rows_ordinate(df, nome_cftc)
        if rows.empty:
            print(f"⚠️ Commodity {simbolo} non trovato.")
            continue
        serie = []
        for _, row in rows.iterrows():
            t = int(row["_rd"].timestamp() * 1000)
            prod = row.get("Prod_Merch_Positions_Long_All", 0) - row.get("Prod_Merch_Positions_Short_All", 0)
            swap = row.get("Swap_Positions_Long_All", 0) - row.get("Swap_Positions_Short_All", 0)
            mm = row.get("Money_Positions_Long_All", 0) - row.get("Money_Positions_Short_All", 0)
            serie.append({"t": t, "prod": float(prod), "swap": float(swap), "mm": float(mm)})
        if serie:
            comm_data[simbolo] = serie
            print(f"✅ Commodity {simbolo}: {len(serie)} settimane")
    return comm_data


def genera_json(fx: dict, comm: dict):
    """Genera cot_data.json nel formato atteso da 4_COT.py."""
    fx_order = ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD", "USD"]
    comm_order = [
        "GOLD", "SILVER", "COPPER", "WTI", "BRENT", "NG",
        "CORN", "WHEAT", "SOYBEANS", "SOYBEAN_OIL", "SOYBEAN_MEAL",
        "OATS", "ROUGH_RICE", "COTTON", "OJ", "LUMBER",
        "LIVE_CATTLE", "LEAN_HOGS",
    ]

    fx_order = [s for s in fx_order if s in fx]
    comm_order = [s for s in comm_order if s in comm]

    max_settimane = 0
    totale_record = 0
    for v in fx.values():
        max_settimane = max(max_settimane, len(v))
        totale_record += len(v)
    for v in comm.values():
        max_settimane = max(max_settimane, len(v))
        totale_record += len(v)

    ultima_data = None
    for v in list(fx.values()) + list(comm.values()):
        if v:
            ultima_data = max(ultima_data or 0, v[-1]["t"])

    data_str = ""
    if ultima_data:
        data_str = datetime.datetime.fromtimestamp(ultima_data / 1000, datetime.timezone.utc).strftime("%Y-%m-%d")

    payload = {
        "meta": {
            "date": data_str,
            "weeks": max_settimane,
            "src": "GITHUB_ACTION" if os.environ.get("GITHUB_ACTIONS") else "LOCAL·python",
            "gen": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "fx_n": len(fx),
            "cm_n": len(comm),
            "rec": totale_record,
        },
        "fx": {k: fx[k] for k in fx_order},
        "comm": {k: comm[k] for k in comm_order},
        "comm_name": COMM_NAMES,
        "fx_order": fx_order,
        "comm_order": comm_order,
    }

    with open(OUTPUT_JSON, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"✅ {OUTPUT_JSON} generato ({len(fx)} forex, {len(comm)} commodities).")


def genera_html(fx: dict, comm: dict):
    """Genera un report HTML statico (opzionale, come fallback)."""
    righe = []
    for nome, serie in fx.items():
        if serie:
            ultimo = serie[-1]
            righe.append(f"<tr><td>{nome}</td><td>Forex</td><td>{ultimo['nc']:,.0f}</td><td>{len(serie)}</td></tr>")
    for nome, serie in comm.items():
        if serie:
            ultimo = serie[-1]
            righe.append(f"<tr><td>{nome}</td><td>Comm</td><td>P:{ultimo['prod']:,.0f} M:{ultimo['mm']:,.0f}</td><td>{len(serie)}</td></tr>")

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>COT Report</title>
<style>
body {{ font-family: sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #334155; padding: 8px 12px; text-align: right; }}
th {{ background: #1e293b; color: #38bdf8; }}
td:first-child {{ text-align: left; font-weight: bold; }}
</style></head><body>
<h1>📊 COT Report – {datetime.date.today()}</h1>
<table><tr><th>Mercato</th><th>Tipo</th><th>Ultima posizione netta</th><th>Settimane</th></tr>
{''.join(righe)}
</table></body></html>"""
    with open(OUTPUT_HTML, "w") as f:
        f.write(html)
    print(f"✅ {OUTPUT_HTML} generato.")


def main():
    print("🚀 COT Build avviato.")
    df = scarica_cot()
    if df.empty:
        print("❌ Nessun dato scaricato. Uscita.")
        return

    fx = processa_forex(df)
    comm = processa_commodities(df)

    if not fx and not comm:
        print("❌ Nessun dato Forex o Commodity processato. Uscita.")
        return

    genera_json(fx, comm)
    genera_html(fx, comm)
    print("🏁 COT Build terminato con successo.")


if __name__ == "__main__":
    main()
