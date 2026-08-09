"""
cot_build.py – Scarica i dati COT dal CFTC e genera cot_data.json
Formato compatibile con pages/4_COT.py
Da eseguire in locale o via GitHub Actions una volta a settimana.
"""

import os
import json
import datetime
import time
import requests
import pandas as pd
import numpy as np

# ===================== CONFIGURAZIONE =====================
COT_URL = "https://www.cftc.gov/files/dea/history/fut_fin_xls_2025.zip"
OUTPUT_JSON = "cot_data.json"
OUTPUT_HTML = "cot_report.html"

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


def scarica_cot() -> pd.DataFrame:
    """Scarica il file Excel dal CFTC e lo carica in un DataFrame."""
    print(f"📡 Scaricando dati COT da {COT_URL}...")
    try:
        df = pd.read_excel(COT_URL, sheet_name="Annual", engine="openpyxl")
        print(f"✅ Dati COT scaricati: {len(df)} righe.")
        return df
    except Exception as e:
        print(f"❌ Errore download COT: {e}")
        # Prova con l'anno precedente se il file non esiste ancora
        try:
            alt_url = COT_URL.replace("2025", "2024")
            print(f"🔄 Tentativo con anno precedente: {alt_url}")
            df = pd.read_excel(alt_url, sheet_name="Annual", engine="openpyxl")
            return df
        except Exception:
            return pd.DataFrame()


def processa_forex(df: pd.DataFrame) -> dict:
    """Estrae le serie storiche Forex (net long non-commercial)."""
    fx_data = {}
    for nome_cftc, simbolo in CFTC_TO_FX.items():
        mask = df["Market_and_Exchange_Names"].str.upper().str.strip() == nome_cftc.upper().strip()
        rows = df[mask].sort_values("Report_Date_as_MM_DD_YYYY")
        if rows.empty:
            print(f"⚠️ Forex {simbolo} non trovato.")
            continue
        serie = []
        for _, row in rows.iterrows():
            try:
                t = int(pd.Timestamp(row["Report_Date_as_MM_DD_YYYY"]).timestamp() * 1000)
            except Exception:
                continue
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
        mask = df["Market_and_Exchange_Names"].str.upper().str.strip() == nome_cftc.upper().strip()
        rows = df[mask].sort_values("Report_Date_as_MM_DD_YYYY")
        if rows.empty:
            print(f"⚠️ Commodity {simbolo} non trovato.")
            continue
        serie = []
        for _, row in rows.iterrows():
            try:
                t = int(pd.Timestamp(row["Report_Date_as_MM_DD_YYYY"]).timestamp() * 1000)
            except Exception:
                continue
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
    # Ordine di visualizzazione (modifica a piacere)
    fx_order = ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD", "USD"]
    comm_order = [
        "GOLD", "SILVER", "COPPER", "WTI", "BRENT", "NG",
        "CORN", "WHEAT", "SOYBEANS", "SOYBEAN_OIL", "SOYBEAN_MEAL",
        "OATS", "ROUGH_RICE", "COTTON", "OJ", "LUMBER",
        "LIVE_CATTLE", "LEAN_HOGS",
    ]

    # Filtra solo quelli presenti
    fx_order = [s for s in fx_order if s in fx]
    comm_order = [s for s in comm_order if s in comm]

    # Calcola meta
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
            ultima_data = v[-1]["t"]

    data_str = ""
    if ultima_data:
        data_str = datetime.datetime.utcfromtimestamp(ultima_data / 1000).strftime("%Y-%m-%d")

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
