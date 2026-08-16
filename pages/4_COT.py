import streamlit as st
import pandas as pd
import numpy as np
import json, os, base64, requests, datetime, html as _html
import io
import zipfile
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from nav import render_navbar, section_header

st.set_page_config(page_title="ARGO COT", layout="wide", page_icon="🛢️")

GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN")
GITHUB_REPO = st.secrets.get("GITHUB_REPO")

WINDOW = 104
MINW = 52

YF_COMM = {
    "GOLD": "GC=F", "SILVER": "SI=F", "COPPER": "HG=F", "PLATINUM": "PL=F", "PALLADIUM": "PA=F",
    "WTI": "CL=F", "BRENT": "BZ=F", "RBOB": "RB=F", "HO": "HO=F", "NG": "NG=F",
    "CORN": "ZC=F", "WHEAT": "ZW=F", "SOYBEANS": "ZS=F", "SOYBEAN_OIL": "ZL=F", "SOYBEAN_MEAL": "ZM=F",
    "OATS": "ZO=F", "ROUGH_RICE": "ZR=F", "COTTON": "CT=F", "COFFEE": "KC=F",
    "SUGAR11": "SB=F", "SUGAR14": None, "COCOA": "CC=F", "OJ": "OJ=F", "LUMBER": "LBS=F",
    "LIVE_CATTLE": "LE=F", "FEEDER_CATTLE": "GF=F", "LEAN_HOGS": "HE=F",
}

CFTC_TO_FX = {
    "EURO FX": "EUR", "BRITISH POUND": "GBP", "JAPANESE YEN": "JPY",
    "AUSTRALIAN DOLLAR": "AUD", "CANADIAN DOLLAR": "CAD",
    "SWISS FRANC": "CHF", "NEW ZEALAND DOLLAR": "NZD", "US DOLLAR INDEX": "USD",
}

CFTC_TO_COMM = {
    "WHEAT": "WHEAT", "CORN": "CORN", "OATS": "OATS", "SOYBEANS": "SOYBEANS",
    "SOYBEAN OIL": "SOYBEAN_OIL", "SOYBEAN MEAL": "SOYBEAN_MEAL",
    "COTTON": "COTTON", "ORANGE JUICE": "OJ", "ROUGH_RICE": "ROUGH_RICE",
    "LIVE CATTLE": "LIVE_CATTLE", "LEAN HOGS": "LEAN_HOGS", "LUMBER": "LUMBER",
    "GOLD": "GOLD", "SILVER": "SILVER", "COPPER": "COPPER",
    "NATURAL GAS": "NG", "CRUDE OIL": "WTI", "BRENT CRUDE OIL": "BRENT",
}

COMM_NAMES = {
    "WHEAT": "🌾 Frumento", "CORN": "🌽 Mais", "OATS": "🥣 Avena",
    "SOYBEANS": "🫘 Soia", "SOYBEAN_OIL": "🫗 Olio di soia", "SOYBEAN_MEAL": "🥜 Farina di soia",
    "COTTON": "🧶 Cotone", "OJ": "🍊 Succo d'arancia", "ROUGH_RICE": "🍚 Riso",
    "LIVE_CATTLE": "🐂 Bovini vivi", "LEAN_HOGS": "🐖 Suini magri", "LUMBER": "🪵 Legname",
    "GOLD": "🥇 Oro", "SILVER": "🥈 Argento", "COPPER": "🟠 Rame",
    "NG": "🔥 Gas Naturale", "WTI": "🛢️ Petrolio WTI", "BRENT": "⛽ Brent",
}

st.markdown("""
<style>
.cot-ticker{border-top:1px solid #1e293b;border-bottom:1px solid #1e293b;overflow:hidden;white-space:nowrap;margin:4px 0 18px;background:#0a0f1a;border-radius:8px}
.cot-track{display:inline-block;padding:7px 0;animation:cotmarq 45s linear infinite}
.cot-ticker:hover .cot-track{animation-play-state:paused}
@keyframes cotmarq{from{transform:translateX(0)}to{transform:translateX(-50%)}}
.cot-tk{display:inline-flex;align-items:center;gap:6px;font-family:'IBM Plex Mono',monospace;font-size:11px;margin:0 14px;color:#94a3b8}
.cot-tk .s{color:#e2e8f0;font-weight:700}
.cot-tk .p{padding:1px 6px;border-radius:3px;font-size:10px}
.cot-tk .p.l{background:rgba(34,197,94,.15);color:#86efac}
.cot-tk .p.s{background:rgba(239,68,68,.15);color:#fca5a5}
.cot-tk .p.n{background:#1e293b;color:#64748b}
.cot-ledger{font-family:'IBM Plex Mono',monospace;font-size:11px;color:#94a3b8;display:flex;gap:22px;flex-wrap:wrap;margin:2px 0 8px}
.cot-ledger .k{color:#64748b}.cot-ledger .v{color:#7dd3fc}.cot-ledger .v.big{color:#fbbf24;font-weight:700}
.cot-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:10px 0}
.cot-met{background:#0b1220;border:1px solid #1e293b;border-radius:8px;padding:9px 11px;transition:transform .15s ease,border-color .2s ease}
.cot-met:hover{transform:translateY(-2px);border-color:#38bdf8}
.cot-met .lab{font-size:9.5px;letter-spacing:.06em;text-transform:uppercase;color:#64748b}
.cot-met .val{font-family:'IBM Plex Mono',monospace;font-size:15px;font-weight:700;margin-top:3px;color:#e2e8f0}
.cot-met .val.pos{color:#86efac}.cot-met .val.neg{color:#fca5a5}.cot-met .val.warn{color:#fbbf24}
.cot-readout{font-family:'IBM Plex Mono',monospace;font-size:12.5px;line-height:1.5;padding:10px 12px;border-radius:8px;border:1px solid #1e293b;background:#0b1220;margin:8px 0}
.cot-readout.red{border-left:3px solid #ef4444}.cot-readout.yellow{border-left:3px solid #f59e0b}.cot-readout.green{border-left:3px solid #22c55e}
.cot-al{border:1px solid #1e293b;border-left-width:4px;border-radius:8px;padding:11px 14px;font-size:12.5px;line-height:1.55;background:#0b1220;margin-bottom:8px}
.cot-al.red{border-left-color:#ef4444}.cot-al.yellow{border-left-color:#f59e0b}.cot-al.green{border-left-color:#22c55e}
.cot-al b{color:#f8fafc}.cot-al .mono{font-family:'IBM Plex Mono',monospace;font-size:11px;color:#94a3b8;display:block;margin-top:3px}
.cot-al .hint{display:block;margin-top:5px;color:#64748b;font-style:italic;font-size:11px}
.cot-chip{display:inline-flex;align-items:center;gap:6px;font-family:'IBM Plex Mono',monospace;font-size:10.5px;padding:5px 9px;border-radius:6px;border:1px solid #1e293b;background:#0b1220;color:#94a3b8;margin:0 5px 6px 0;transition:transform .12s ease,border-color .15s ease}
.cot-chip:hover{transform:translateY(-2px)}
.cot-chip .cd{width:8px;height:8px;border-radius:2px}
.cot-chip .cs{font-weight:700;color:#e2e8f0}
.cot-chip.t-green{border-color:rgba(34,197,94,.4)}.cot-chip.t-green .cd{background:#22c55e}
.cot-chip.t-red{border-color:rgba(239,68,68,.4)}.cot-chip.t-red .cd{background:#ef4444}
.cot-chip.t-yellow{border-color:rgba(245,158,11,.4)}.cot-chip.t-yellow .cd{background:#f59e0b}
.cot-chip.t-ice{border-color:rgba(56,189,248,.4)}.cot-chip.t-ice .cd{background:#38bdf8}
.cot-chip.t-muted{opacity:.55}.cot-chip.t-muted .cd{background:#475569}
</style>
""", unsafe_allow_html=True)

render_navbar("cot", hide_sidebar=True)
section_header("Commitments of Traders", "COT Plate · Forex & Materie Prime")


@st.cache_data(ttl=3600)
def carica_cot():
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return None
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/cot_data.json"
        r = requests.get(url, headers={"Authorization": f"token {GITHUB_TOKEN}"}, timeout=30)
        if r.status_code != 200:
            return None
        return json.loads(base64.b64decode(r.json()["content"]).decode())
    except Exception as e:
        print("Errore lettura cot_data.json:", e)
        return None


@st.cache_data(ttl=43200)
def prezzo_yf(sym):
    if not sym:
        return None
    try:
        h = yf.download(sym, period="3y", interval="1d", progress=False, auto_adjust=True)
        if h is None or h.empty:
            return None
        if isinstance(h.columns, pd.MultiIndex):
            h.columns = h.columns.droplevel(-1)
        c = h["Close"].dropna()
        if c.index.tz is not None:
            c = c.tz_localize(None)
        return c
    except Exception:
        return None


DATA = carica_cot()


# ================================================================
# AGGIORNAMENTO MANUALE GUIDATA: link download + upload zip + merge
# ================================================================
def leggi_zip_bytes(content: bytes) -> pd.DataFrame:
    """Estrae il foglio Annual da uno zip CFTC ricevuto come bytes."""
    zf = zipfile.ZipFile(io.BytesIO(content))
    nomi = [n for n in zf.namelist() if n.lower().endswith((".xls", ".xlsx"))]
    if not nomi:
        raise RuntimeError("Nessun file .xls dentro lo zip")
    inner = zf.read(nomi[0])
    errs = []
    for eng in (None, "openpyxl", "xlrd"):
        try:
            return pd.read_excel(io.BytesIO(inner), sheet_name="Annual", engine=eng)
        except Exception as e:
            errs.append(f"{eng or 'auto'}: {e}")
    raise RuntimeError("Lettura Annual fallita -> " + " | ".join(errs))


def _rows_ordinate(df: pd.DataFrame, nome_cftc: str) -> pd.DataFrame:
    mask = df["Market_and_Exchange_Names"].str.upper().str.strip() == nome_cftc.upper().strip()
    rows = df[mask].copy()
    rows["_rd"] = pd.to_datetime(rows["Report_Date_as_MM_DD_YYYY"], errors="coerce")
    return rows.dropna(subset=["_rd"]).sort_values("_rd")


def processa_dfs(df: pd.DataFrame):
    """Da DataFrame CFTC a serie fx/comm nel formato cot_data.json."""
    fx = {}
    for nome_cftc, simbolo in CFTC_TO_FX.items():
        rows = _rows_ordinate(df, nome_cftc)
        if rows.empty:
            continue
        serie = []
        for _, row in rows.iterrows():
            t = int(row["_rd"].timestamp() * 1000)
            nc = row.get("NonComm_Positions_Long_All", 0) - row.get("NonComm_Positions_Short_All", 0)
            serie.append({"t": t, "nc": float(nc)})
        if serie:
            fx[simbolo] = serie

    comm = {}
    for nome_cftc, simbolo in CFTC_TO_COMM.items():
        rows = _rows_ordinate(df, nome_cftc)
        if rows.empty:
            continue
        serie = []
        for _, row in rows.iterrows():
            t = int(row["_rd"].timestamp() * 1000)
            prod = row.get("Prod_Merch_Positions_Long_All", 0) - row.get("Prod_Merch_Positions_Short_All", 0)
            swap = row.get("Swap_Positions_Long_All", 0) - row.get("Swap_Positions_Short_All", 0)
            mm = row.get("Money_Positions_Long_All", 0) - row.get("Money_Positions_Short_All", 0)
            serie.append({"t": t, "prod": float(prod), "swap": float(swap), "mm": float(mm)})
        if serie:
            comm[simbolo] = serie
    return fx, comm


def merge_con_esistente(existing_fx, existing_comm, new_fx, new_comm):
    """Aggiunge allo storico salvato solo le settimane piu recenti (dedup per t)."""
    def _merge(old, new):
        out = {k: list(v) for k, v in (old or {}).items()}
        for k, v in (new or {}).items():
            if k in out and out[k]:
                last_t = max(x["t"] for x in out[k])
                add = [x for x in v if x["t"] > last_t]
                out[k] = out[k] + add
            else:
                out[k] = list(v)
        return out
    return _merge(existing_fx, new_fx), _merge(existing_comm, new_comm)


def pubblica_payload(fx, comm):
    fx_order = [s for s in ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD", "USD"] if s in fx]
    comm_order = [s for s in [
        "GOLD", "SILVER", "COPPER", "WTI", "BRENT", "NG",
        "CORN", "WHEAT", "SOYBEANS", "SOYBEAN_OIL", "SOYBEAN_MEAL",
        "OATS", "ROUGH_RICE", "COTTON", "OJ", "LUMBER",
        "LIVE_CATTLE", "LEAN_HOGS",
    ] if s in comm]

    max_settimane = 0
    totale_record = 0
    for v in list(fx.values()) + list(comm.values()):
        max_settimane = max(max_settimane, len(v))
        totale_record += len(v)

    ultima_data = None
    for v in list(fx.values()) + list(comm.values()):
        if v:
            ultima_data = max(ultima_data or 0, v[-1]["t"])
    data_str = datetime.datetime.fromtimestamp(ultima_data / 1000, datetime.timezone.utc).strftime("%Y-%m-%d") if ultima_data else ""

    payload = {
        "meta": {
            "date": data_str,
            "weeks": max_settimane,
            "src": "PORTALE·upload",
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

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/cot_data.json"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    r = requests.get(url, headers=headers)
    sha = r.json().get("sha") if r.status_code == 200 else None
    put_payload = {
        "message": f"chore(cot): aggiornamento manuale {datetime.date.today().isoformat()}",
        "content": base64.b64encode(json.dumps(payload, indent=2).encode()).decode(),
        "branch": "main",
    }
    if sha:
        put_payload["sha"] = sha
    r = requests.put(url, headers=headers, json=put_payload)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Commit su GitHub fallito: {r.status_code} {r.text[:200]}")
    return payload


if not DATA:
    st.info("🛢️ **Nessun dato COT sul repo.** Usa il pannello **📥 Aggiornamento manuale** qui sotto: scarica i zip dal tuo browser e caricali qui.")

_anno = datetime.date.today().year
with st.expander("📥 Aggiornamento manuale (download dal browser + upload)", expanded=(DATA is None)):
    st.markdown(
        f"**1️⃣ Scarica i zip dal sito CFTC** (il tuo browser non viene bloccato):\n\n"
        f"- 🔗 [fut_fin_xls_{_anno}.zip](https://www.cftc.gov/files/dea/history/fut_fin_xls_{_anno}.zip) — **basta questo**: lo storico salvato viene conservato e aggiornato\n"
        f"- 🔗 [fut_fin_xls_{_anno - 1}.zip](https://www.cftc.gov/files/dea/history/fut_fin_xls_{_anno - 1}.zip) — opzionale, solo per ricostruzione da zero\n\n"
        f"**2️⃣ Carica qui i file scaricati** (anche uno solo), poi premi **Processa**."
    )
    uploaded = st.file_uploader("Zip CFTC (.zip)", type=["zip"], accept_multiple_files=True, label_visibility="collapsed")
    if st.button("⚙️ Processa e pubblica su GitHub", type="primary", disabled=(not uploaded)):
        with st.spinner("Lettura zip + merge con storico + commit..."):
            try:
                frames = []
                for up in uploaded:
                    frames.append(leggi_zip_bytes(up.read()))
                df_new = pd.concat(frames, ignore_index=True)
                df_new = df_new.drop_duplicates(subset=["Market_and_Exchange_Names", "Report_Date_as_MM_DD_YYYY"])
                new_fx, new_comm = processa_dfs(df_new)
                if not new_fx and not new_comm:
                    raise RuntimeError("Nessun mercato riconosciuto nei zip caricati.")
                old_fx = DATA.get("fx", {}) if DATA else {}
                old_comm = DATA.get("comm", {}) if DATA else {}
                fx, comm = merge_con_esistente(old_fx, old_comm, new_fx, new_comm)
                payload = pubblica_payload(fx, comm)
                st.cache_data.clear()
                st.success(f"✅ COT pubblicato: report del {payload['meta']['date']} · {payload['meta']['weeks']} settimane · {payload['meta']['rec']} record.")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Elaborazione fallita: {e}")

if not DATA:
    st.stop()

META = DATA["meta"]; FX = DATA["fx"]; COMM = DATA["comm"]
COMM_NAME = DATA.get("comm_name", {}); FX_ORDER = DATA.get("fx_order", []); COMM_ORDER = DATA.get("comm_order", [])

try:
    d_rep = datetime.date.fromisoformat(META["date"])
    giorni = (datetime.date.today() - d_rep).days
    if giorni > 12:
        st.warning(f"⚠️ Dati COT del **{META['date']}** ({giorni} giorni fa): il report CFTC esce il venerdì, usa **📥 Aggiornamento manuale**.")
except Exception:
    pass

st.markdown(
    f'<div class="cot-ledger">'
    f'<span><span class="k">report_date</span> <span class="v big">{META["date"]}</span></span>'
    f'<span><span class="k">window</span> <span class="v">{META["weeks"]} sett.</span></span>'
    f'<span><span class="k">records</span> <span class="v">{META["rec"]}</span></span>'
    f'<span><span class="k">generated</span> <span class="v">{META["gen"]}</span></span>'
    f'<span><span class="k">source</span> <span class="v">{META["src"]}</span></span>'
    f'</div>', unsafe_allow_html=True)


def series(a, k):
    return [x[k] for x in a[-WINDOW:]]

def percentile(a, v):
    if not a: return 50.0
    s = sorted(a); b = 0
    for x in s:
        if x < v: b += 1
        else: break
    return b / len(s) * 100

def zscore(a, w=52):
    r = a[-w:]
    if len(r) < 5: return 0.0
    m = sum(r) / len(r)
    sd = (sum((x - m) ** 2 for x in r) / len(r)) ** .5
    return 0.0 if sd == 0 else (a[-1] - m) / sd

def deriv(a, w=2):
    if len(a) < w + 1: return 0.0
    r = a[-w - 1:]; return r[-1] - r[0]

def reversing(a, w=2):
    if len(a) < w + 1: return False
    r = a[-w - 1:]; d = [r[i] - r[i - 1] for i in range(1, len(r))]
    return all(x > 0 for x in d) or all(x < 0 for x in d)

def comm_state(sym):
    """Stato COT di una commodity.
    REGOLA HOT ALLARGATA: Producer estremo (pP<10 o pP>90) => hot anche senza Managed estremo."""
    arr = COMM.get(sym) or []
    if len(arr) < MINW:
        return {"key": "flat", "tone": "muted", "pP": 50, "pM": 50, "pS": 50, "dP": 0, "dM": 0, "revP": False}
    pA = series(arr, "prod"); mA = series(arr, "mm"); sA = series(arr, "swap")
    pP = percentile(pA, pA[-1]); pM = percentile(mA, mA[-1]); pS = percentile(sA, sA[-1])
    dP = deriv(pA); dM = deriv(mA); revP = reversing(pA)
    if pP < 20 and pM > 65: key, tone = "bull", "green"
    elif pP > 80 and pM < 35: key, tone = "bear", "red"
    elif (pM > 85 or pM < 15) and not revP: key, tone = "watch", "yellow"
    elif abs(dM) > abs(dP) * 1.2 and 15 <= pM <= 85: key, tone = "trend", "ice"
    elif (pP < 10 or pP > 90): key, tone = "hot_producer", "yellow"
    else: key, tone = "flat", "muted"
    return {"key": key, "tone": tone, "pP": pP, "pM": pM, "pS": pS, "dP": dP, "dM": dM, "revP": revP}


def build_ticker():
    items = []
    for s in FX_ORDER:
        a = FX.get(s) or []
        if len(a) < MINW: continue
        v = series(a, "nc"); p = percentile(v, v[-1])
        cls = "l" if p >= 66 else ("s" if p <= 34 else "n")
        items.append(f'<span class="cot-tk"><span class="s">{s}</span><span class="p {cls}">{p:.0f}°</span></span>')
    for s in COMM_ORDER:
        a = COMM.get(s) or []
        if len(a) < MINW: continue
        v = series(a, "prod"); p = percentile(v, v[-1])
        cls = "l" if p <= 30 else ("s" if p >= 70 else "n")
        items.append(f'<span class="cot-tk"><span class="s">{s}</span><span class="p {cls}">P{p:.0f}°</span></span>')
    if not items: return
    inner = "".join(items)
    st.markdown(f'<div class="cot-ticker"><div class="cot-track">{inner}{inner}</div></div>', unsafe_allow_html=True)

build_ticker()

tab_fx, tab_cm = st.tabs(["💱 Forex · Leveraged Money", "🛢️ Materie prime · tre categorie"])

# ================================================================
# FOREX
# ================================================================
with tab_fx:
    syms = [s for s in FX_ORDER if len(FX.get(s) or []) >= MINW]
    if not syms:
        st.info("Nessun dato Forex valido: servono ≥ 52 settimane (usa 📥 Aggiornamento manuale).")
    else:
        P = {}; D = {}
        for s in syms:
            v = series(FX[s], "nc"); P[s] = percentile(v, v[-1]); D[s] = deriv(v)

        z = []; txt = []; cust = []
        maxD, maxPair, maxSign = 0, "", 1
        for rs in syms:
            zr, tr, cr = [], [], []
            for cs in syms:
                if rs == cs:
                    zr.append(None); tr.append("·"); cr.append("—")
                else:
                    diff = P[rs] - P[cs]; dd = D[rs] - D[cs]
                    if abs(diff) > maxD: maxD, maxPair, maxSign = abs(diff), f"{rs}/{cs}", (1 if diff >= 0 else -1)
                    zr.append(diff); tr.append(f"{diff:+.0f}")
                    verso = "LONG" if diff >= 0 else "SHORT"
                    cr.append(f"<b>{verso} {rs}/{cs}</b> · Δperc {diff:+.0f} · {rs} {P[rs]:.0f}° vs {cs} {P[cs]:.0f}° · deriv {dd:+.0f}")
            z.append(zr); txt.append(tr); cust.append(cr)

        c1, c2 = st.columns([1.6, 1], gap="large")
        with c1:
            st.markdown("**Matrice forza relativa** — cella = P(riga) − P(colonna) su Leveraged Money net. Passa il mouse per il verso operativo della coppia.")
            fig = go.Figure(go.Heatmap(
                z=z, x=syms, y=syms, text=txt, texttemplate="%{text}",
                textfont={"size": 12, "family": "IBM Plex Mono", "color": "#e2e8f0"},
                customdata=cust, hovertemplate="%{customdata}<extra></extra>",
                zmin=-100, zmax=100, xgap=3, ygap=3,
                colorscale=[
                    [0.0, "#e0685a"], [0.05, "#d65a4a"], [0.10, "#b0473a"], [0.20, "#8a3a30"],
                    [0.25, "#232a34"], [0.5, "#232a34"], [0.75, "#232a34"],
                    [0.80, "#35604a"], [0.90, "#418a5f"], [0.95, "#4fae7e"], [1.0, "#5cc48e"],
                ],
                showscale=False,
            ))
            fig.update_layout(
                template="plotly_dark", height=430, margin=dict(l=10, r=10, t=10, b=10),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                xaxis={"side": "top", "tickfont": {"family": "IBM Plex Mono", "color": "#7dd3fc"}},
                yaxis={"autorange": "reversed", "tickfont": {"family": "IBM Plex Mono", "color": "#7dd3fc"}},
            )
            st.plotly_chart(fig, use_container_width=True)
            st.markdown(
                f'<div class="cot-readout {"green" if maxSign>0 else "red"}">Coppia più sbilanciata: '
                f'<b>{"LONG" if maxSign>0 else "SHORT"} {maxPair}</b> · Δperc {maxD:.0f}° · soglie alert ±80°</div>',
                unsafe_allow_html=True)
        with c2:
            st.markdown("**Ranking valute** — percentile del net speculativo. Destra = euforia long, sinistra = panico short.")
            order = sorted(syms, key=lambda s: P[s], reverse=True)
            figr = go.Figure(go.Bar(
                y=order, x=[P[s] - 50 for s in order], orientation="h",
                marker={"color": ["#4fae7e" if P[s] >= 66 else ("#d65a4a" if P[s] <= 34 else "#f2c200") for s in order]},
                text=[f"{P[s]:.0f}°" for s in order], textposition="outside",
                textfont={"family": "IBM Plex Mono", "size": 11, "color": "#cbd5e1"},
            ))
            figr.update_layout(template="plotly_dark", height=330, margin=dict(l=10, r=10, t=10, b=10),
                               paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                               xaxis={"range": [-55, 55], "showgrid": False, "visible": False},
                               yaxis={"autorange": "reversed", "tickfont": {"family": "IBM Plex Mono", "color": "#7dd3fc"}})
            st.plotly_chart(figr, use_container_width=True)

            als = []
            for i, a in enumerate(syms):
                for b in syms:
                    if a == b: continue
                    diff = P[a] - P[b]
                    if abs(diff) >= 80:
                        verso = "LONG" if diff > 0 else "SHORT"
                        dd = D[a] - D[b]
                        als.append(f'<div class="cot-al red"><b>{verso} {a}/{b}</b> · squilibrio estremo'
                                   f'<span class="mono">Δperc {diff:.0f} · {a} {P[a]:.0f}° · {b} {P[b]:.0f}° · deriv {dd:+.0f}</span>'
                                   f'<span class="hint">Conferma con setup volumetrico su grafico prima di operare.</span></div>')
            if not als:
                als.append('<div class="cot-al green">Nessun differenziale oltre ±80°.</div>')
            st.markdown("".join(als), unsafe_allow_html=True)

# ================================================================
# MATERIE PRIME
# ================================================================
with tab_cm:
    stati = {s: comm_state(s) for s in COMM_ORDER}
    mk = [s for s in COMM_ORDER if len(COMM.get(s) or []) >= MINW]
    if not mk:
        st.info("Nessun dato Disaggregated valido: servono ≥ 52 settimane (usa 📥 Aggiornamento manuale).")
    else:
        if "cot_filter" not in st.session_state: st.session_state["cot_filter"] = "hot"
        bf1, bf2, bf3, bf4 = st.columns([1, 1, 1, 5])
        for col, key, lab in ((bf1, "hot", "CALDI"), (bf2, "all", "TUTTI"), (bf3, "bull", "▲"), (bf4, "bear", "▼")):
            if col.button(lab, key=f"cotf_{key}", type="primary" if st.session_state["cot_filter"] == key else "secondary"):
                st.session_state["cot_filter"] = key
                st.rerun()
        flt = st.session_state["cot_filter"]
        visible = [s for s in mk if (flt == "all") or (flt == "hot" and stati[s]["tone"] != "muted") or (flt == "bull" and stati[s]["key"] == "bull") or (flt == "bear" and stati[s]["key"] == "bear")]
        if not visible: visible = mk

        chips = "".join(
            f'<span class="cot-chip t-{stati[s]["tone"]}"><span class="cd"></span><span class="cs">{s}</span>'
            f'<span>{stati[s]["pP"]:.0f}</span></span>' for s in visible)
        hot_n = sum(1 for s in mk if stati[s]["tone"] != "muted")
        st.markdown(f'<div style="margin:6px 0 4px">{chips}</div>'
                    f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:10.5px;color:#64748b;margin-bottom:10px">{hot_n} / {len(mk)} con lettura attiva</div>',
                    unsafe_allow_html=True)

        opts = {s: (COMM_NAME.get(s) or s) for s in mk}   # menu sempre completo, svincolato dal filtro
        if "cot_market" not in st.session_state or st.session_state["cot_market"] not in opts:
            st.session_state["cot_market"] = (visible[0] if visible else mk[0])
        sym = st.selectbox("Mercato", list(opts.keys()), format_func=lambda s: opts[s], label_visibility="collapsed")

        arr = COMM[sym]
        pA = series(arr, "prod"); mA = series(arr, "mm"); sA = series(arr, "swap")
        S = stati[sym]
        pP, pM, pS, dP, dM, revP = S["pP"], S["pM"], S["pS"], S["dP"], S["dM"], S["revP"]
        zP, zM = zscore(pA), zscore(mA); dS = deriv(sA)

        g1, g2 = st.columns([1.6, 1], gap="large")
        with g1:
            st.markdown(f"**Trasferimento rischio — {COMM_NAME.get(sym, sym)}** · {len(arr)} sett. · la linea ambra (asse destro) è il **prezzo del future front‑month**, allineato alla settimana CFTC.")
            show_price = st.checkbox("Sovrapponi prezzo dell'asset (asse destro)", value=True, key="cot_price_on")
            figc = make_subplots(specs=[[{"secondary_y": True}]])
            figc.add_trace(go.Scatter(y=pA, name="Producer/Merchant", line={"color": "#d65a4a", "width": 2}, fill="tozeroy", fillcolor="rgba(214,90,74,.08)"), secondary_y=False)
            figc.add_trace(go.Scatter(y=mA, name="Managed Money", line={"color": "#4fae7e", "width": 2}), secondary_y=False)
            figc.add_trace(go.Scatter(y=sA, name="Swap Dealer", line={"color": "#6fcfcf", "width": 1.5, "dash": "dash"}), secondary_y=False)

            price_note = ""
            if show_price:
                close = prezzo_yf(YF_COMM.get(sym))
                if close is not None and len(close) > 1:
                    times = [x["t"] for x in arr[-WINDOW:]]
                    py = []
                    for t in times:
                        ts = pd.Timestamp(int(t), unit="ms")
                        v = close.asof(ts)
                        py.append(None if pd.isna(v) else float(v))
                    figc.add_trace(go.Scatter(
                        y=py, name="Prezzo (front-month)",
                        line={"color": "#fbbf24", "width": 2.4},
                        hovertemplate="prezzo %{y:.2f}<extra></extra>"), secondary_y=True)
                else:
                    price_note = f"Prezzo non disponibile per {sym} (nessun future front‑month su yfinance)."

            figc.update_layout(template="plotly_dark", height=340, margin=dict(l=10, r=10, t=10, b=10),
                               paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                               legend={"orientation": "h", "y": 1.14, "font": {"family": "IBM Plex Mono", "size": 10.5}},
                               xaxis={"title": "settimane (ultime 104)", "tickfont": {"size": 9.5, "color": "#64748b"}},
                               )
            figc.update_yaxes(title_text="contratti", secondary_y=False,
                              tickfont={"family": "IBM Plex Mono", "size": 10, "color": "#64748b"},
                              gridcolor="rgba(255,255,255,.05)")
            figc.update_yaxes(title_text="prezzo", secondary_y=True, showgrid=False,
                              tickfont={"family": "IBM Plex Mono", "size": 10, "color": "#fbbf24"})
            st.plotly_chart(figc, use_container_width=True)
            if price_note:
                st.caption(price_note)

            cls_v = "pos" if dP >= 0 else "neg"; cls_m = "pos" if dM >= 0 else "neg"
            st.markdown(
                f'<div class="cot-metrics">'
                f'<div class="cot-met"><div class="lab">Producer perc</div><div class="val {"warn" if (pP<10 or pP>90) else ""}">{pP:.0f}°</div></div>'
                f'<div class="cot-met"><div class="lab">Managed perc</div><div class="val {"warn" if (pM<10 or pM>90) else ""}">{pM:.0f}°</div></div>'
                f'<div class="cot-met"><div class="lab">Swap perc</div><div class="val">{pS:.0f}°</div></div>'
                f'<div class="cot-met"><div class="lab">Prod inverte</div><div class="val {"warn" if revP else ""}">{"SÌ ✓" if revP else "no"}</div></div>'
                f'<div class="cot-met"><div class="lab">Z-score Prod</div><div class="val {"warn" if abs(zP)>2 else ""}">{zP:.2f}</div></div>'
                f'<div class="cot-met"><div class="lab">Z-score MM</div><div class="val {"warn" if abs(zM)>2 else ""}">{zM:.2f}</div></div>'
                f'<div class="cot-met"><div class="lab">Δ Prod 2w</div><div class="val {cls_v}">{dP:+.0f}</div></div>'
                f'<div class="cot-met"><div class="lab">Δ MM 2w</div><div class="val {cls_m}">{dM:+.0f}</div></div>'
                f'</div>', unsafe_allow_html=True)

            opp = (pP < 30 and pM > 70) or (pP > 70 and pM < 30)
            if pP < 20 and pM > 65:
                vcls = "red" if revP else "yellow"
                vtxt = (f"<b style='color:#86efac'>CONTESTO RIALZISTA ATTIVO</b> · Producer depresso ({pP:.0f}°) e <b>in inversione</b>: il rischio si trasferisce. Setup di contesto long → cerca conferma volumetrica."
                        if revP else
                        f"<b style='color:#fbbf24'>TENSIONE RIALZISTA</b> · Producer molto short ({pP:.0f}°) vs Managed long ({pM:.0f}°). <b>Non è ancora long</b>: attendi che la linea rossa salga (producer inverte).")
            elif pP > 80 and pM < 35:
                vcls = "red" if revP else "yellow"
                vtxt = (f"<b style='color:#fca5a5'>CONTESTO RIBASSISTA ATTIVO</b> · Producer {pP:.0f}° in inversione verso più copertura + Managed short ({pM:.0f}°). Setup di contesto short."
                        if revP else
                        f"<b style='color:#fbbf24'>TENSIONE RIBASSISTA</b> · Producer {pP:.0f}° vs Managed {pM:.0f}°. Attendi che la linea rossa scenda (producer riprende a coprire).")
            elif (pM > 85 or pM < 15) and not revP:
                vcls, vtxt = "yellow", (f"<b style='color:#fbbf24'>SPECULATORI A ESTREMO</b> · Managed {'max long' if pM>85 else 'max short'} ({pM:.0f}°) ma producer non inverte: trend maturo → <b>non inseguirlo, non invertirlo</b>. Watchlist.")
            elif abs(dM) > abs(dP) * 1.2 and 15 <= pM <= 85:
                vcls, vtxt = "green", (f"<b style='color:#7dd3fc'>TREND SPECULATIVO IN CORSO</b> · Managed {'accumula long' if dM>0 else 'accumula short'} (Δ {dM:+.0f}) senza estremi: trend vivo → <b>non operare contro</b>.")
            elif (pP < 10 or pP > 90):
                vcls, vtxt = "yellow", (f"<b style='color:#fbbf24'>PRODUCER ESTREMO</b> · Producer a {pP:.0f}° con Managed neutro ({pM:.0f}°): copertura commerciale anomala → <b>monitora quando la linea rossa inverte</b> come anticipatore.")
            else:
                vcls, vtxt = "green", (f"<b>NESSUNA LETTURA DOMINANTE</b> · Producer {pP:.0f}° · Managed {pM:.0f}° · Swap {pS:.0f}°. Nessun trasferimento netto: stai fermo.")
            st.markdown(f'<div class="cot-readout {vcls}">{vtxt}</div>', unsafe_allow_html=True)

            als = []
            if (pP < 10 or pP > 90) and (pM < 10 or pM > 90) and opp:
                d2 = "RIALZISTA" if pP < 10 else "RIBASSISTA"
                als.append(f'<div class="cot-al {"red" if revP else "yellow"}"><b>{d2} · trasferimento rischio estremo</b>'
                           f'<span class="mono">Producer {pP:.0f}° vs Managed {pM:.0f}° · ΔProd {dP:+.0f} · ΔMM {dM:+.0f} · ΔSwap {dS:+.0f}</span>'
                           + (f'<span class="hint">Producer in inversione: segnale di contesto forte.</span>' if revP else '<span class="hint">Estremo ma Producer non ancora in inversione → sola watchlist.</span>')
                           + '<span class="hint">Conferma divergenza prezzo/volumi su TradingView.</span></div>')
            elif (pP < 10 or pP > 90):
                als.append(f'<div class="cot-al yellow"><b>PRODUCER ESTREMO ({pP:.0f}°)</b>'
                           f'<span class="mono">ΔProd {dP:+.0f} · Managed {pM:.0f}° (neutro) · Z-prod {zP:.2f}</span>'
                           f'<span class="hint">Copertura commerciale a livello storico estremo: attendi che la linea rossa inverta direzione per il timing.</span></div>')
            if abs(zP) > 2 or abs(zM) > 2:
                als.append(f'<div class="cot-al yellow"><b>Z-score oltre ±2σ</b><span class="mono">Prod {zP:.2f} · MM {zM:.2f}</span><span class="hint">Attenzione al cambio di regime.</span></div>')
            if not als:
                als.append(f'<div class="cot-al green">Nessuna configurazione estrema su {sym}.</div>')
            st.markdown("".join(als), unsafe_allow_html=True)

        with g2:
            with st.expander("📖 Come leggere le 3 linee + prezzo", expanded=True):
                st.markdown(
                    "- 🟥 **Producer/Merchant** — strutturalmente *short*: il segnale è il **percentile**. Linea che **sale** = contesto di **bottom**; che **scende** = contesto di **top**.\n"
                    "- 🟩 **Managed Money** — segno leggibile: sopra zero = long, sotto = short. A **estremi** il trend è maturo.\n"
                    "- 🟦 **Swap Dealer** — rumoroso; utile solo se cambia segno / riduce.\n"
                    "- 🟨 **Prezzo (asse destro)** — future front‑month. Serve per la **divergenza**: prezzo su nuovi massimi ma Managed no = carburante in calo.",
                    unsafe_allow_html=False)
            with st.expander("⚙️ Configurazioni operative"):
                st.markdown(
                    "- **▲ RIALZISTA** — Producer ai minimi + Managed ai massimi = tensione; diventa long **solo quando il Producer inverte**.\n"
                    "- **▼ RIBASSISTA** — speculare: conferma quando il Producer riprende a coprire.\n"
                    "- **🔥 PRODUCER ESTREMO** — solo la linea rossa al limite storico: i commerciali prendono posizione senza precedenti; aspetta che la linea inverta per il timing.\n"
                    "- **TREND VIVO** — Managed in trend *senza* estremi e Producer che accompagna → non operare contro.\n"
                    "- **DIVERGENZA** — prezzo fa nuovi massimi ma il Managed no → carburante in calo (leggibile sull'asse destro).",
                    unsafe_allow_html=False)
