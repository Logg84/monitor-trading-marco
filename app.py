"""
Watchlist — home. Tabella 👤/🤖 con zone volumetriche, VWAP ancorati,
segnale, trimestrali; livelli L1/L2/L3; storico alert; analisi singola;
lettura grafico Groq (opzionale, manuale se non disponibile).
"""
import streamlit as st
import plotly.graph_objects as go
import pandas as pd

st.set_page_config(page_title="Watchlist", page_icon="📊", layout="wide",
                   initial_sidebar_state="collapsed")

from ui.theme import inject_css, COLORS, style_fig
from ui.nav import render_navbar, sidebar_nav
from core.data_engine import (
    get_prices, get_prices_long, atr, vwap_anchored,
    volume_zones, structural_anchors, earnings_dates_list,
    health_check, bottom_score, rebound_signal, earnings_snapshot,
    build_universe, resolve_ticker,
)
from core.watchlist_io import (
    load_watchlist, add_entry, remove_entry, touch_review, update_levels,
    is_stale, reconcile,
)
from core.alerts import load_alert_state
from core.vision import read_chart

if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = True

inject_css(dark=st.session_state.dark_mode)
render_navbar(title="Watchlist")
sidebar_nav()

def zstr(z: dict | None) -> str:
    if z is None:
        return "—"
    return f"{z['lo']:.2f}–{z['hi']:.2f} ·{z['score']}"

def build_analysis(ticker: str) -> dict | None:
    try:
        df = get_prices(ticker)
    except Exception:
        return None
    vwap60 = vwap_anchored(df)
    a20 = atr(df)
    price = float(df["Close"].iloc[-1])
    ath = float(df["Close"].max())
    dd = (price / ath - 1) * 100

    try:
        wdf = get_prices_long(ticker)
    except Exception:
        wdf = df
    zones = volume_zones(wdf)
    anchors = structural_anchors(wdf, earnings=earnings_dates_list(ticker))
    bs = bottom_score(df, zones=zones)

    in_lbl = ""
    for zi, z in enumerate(zones, 1):
        if z["lo"] <= price <= z["hi"]:
            in_lbl = f"Z{zi}"
            break
    vwa1 = anchors[0]["vwap"] if anchors else None
    below = bool((vwa1 is not None and price <= vwa1) or price <= vwap60)

    return {
        "df": df, "vwap60": vwap60, "zones": zones, "anchors": anchors,
        "bs": bs, "price": price, "dd": dd, "in_lbl": in_lbl,
        "signal": rebound_signal(dd, bs["decel"], bs["rsi"], bool(in_lbl), below),
        "es": earnings_snapshot(ticker),
    }

st.markdown("## Watchlist")
st.caption(
    "Zone volumetriche su settimanale lungo: score = 60% dimensione + 40% recency (half-life 4y). "
    "VWA1-3: VWAP ancorati a minimi strutturali (≥26 sett. apart), bonus se a ±30gg da trimestrale. "
    "Segnale 🟢 = DD≤−20% + decel>0 + RSI<45 + (in zona o ≤VWA1). Lettura, mai ordine."
)
entries = load_watchlist()

analyses = {}
for e in entries:
    a = build_analysis(e["ticker"])
    if a is not None:
        analyses[e["ticker"]] = a

metrics = {
    t: {"vwap": round(a["vwap60"], 4),
        "poc_auto": round(a["zones"][0]["center"], 4) if a["zones"] else None,
        "drawdown": a["dd"]}
    for t, a in analyses.items()
}
entries, msgs = reconcile(entries, {k: v for k, v in metrics.items() if v})
for m in msgs:
    st.warning(m)

with st.expander("➕ Aggiungi titolo (👤 manuale)"):
    with st.form("add_form"):
        c1, c2 = st.columns([2, 1])
        new_ticker = c1.text_input("Ticker (es. CPR.MI o CPR)", value="")
        new_poc = c2.number_input("POC manuale (opzionale)", value=0.0, step=0.1)
        submitted = st.form_submit_button("Aggiungi", type="primary")
        if submitted and new_ticker.strip():
            t = resolve_ticker(new_ticker) or new_ticker.strip().upper()
            add_entry(t, origin="manual", poc=new_poc if new_poc > 0 else None)
            st.rerun()

if not entries:
    st.info("Watchlist vuota. Aggiungi un titolo o promuovilo dallo Screening.")
else:
    rows = []
    for e in entries:
        a = analyses.get(e["ticker"])
        if a is None:
            continue
        es = a["es"]
        trim = "✅" if es["positive"] is True else ("❌" if es["positive"] is False else "n/d")
        vwa1 = a["anchors"][0]["vwap"] if a["anchors"] else None
        rows.append({
            "Orig.": "👤" if e["origin"] == "manual" else "🤖",
            "Ticker": e["ticker"],
            "Prezzo": round(a["price"], 2),
            "DD%": round(a["dd"], 1),
            "RSI": round(a["bs"]["rsi"], 0),
            "VWAP60": round(a["vwap60"], 2),
            "VWA1": round(vwa1, 2) if vwa1 else "—",
            "VWA2": round(a["anchors"][1]["vwap"], 2) if len(a["anchors"]) > 1 else "—",
            "VWA3": round(a["anchors"][2]["vwap"], 2) if len(a["anchors"]) > 2 else "—",
            "Z1": zstr(a["zones"][0] if a["zones"] else None),
            "Z2": zstr(a["zones"][1] if len(a["zones"]) > 1 else None),
            "In zona": a["in_lbl"],
            "Segnale": a["signal"],
            "Trim.": trim,
            "Bottom": a["bs"]["score"],
            "Stale": "⚠️" if is_stale(e) else "",
        })

    if rows:
        sc1, sc2 = st.columns([2, 1])
        sort_col = sc1.selectbox(
            "Ordina per",
            ["Bottom", "DD%", "RSI", "Prezzo", "VWA1", "Ticker"],
            index=0, key="wl_sort",
        )
        sort_dir = sc2.radio("Direzione", ["Discendente", "Ascendente"],
                             horizontal=True, key="wl_dir")
        df_w = pd.DataFrame(rows).sort_values(
            sort_col, ascending=(sort_dir == "Ascendente")
        ).reset_index(drop=True)
        st.dataframe(df_w, use_container_width=True, hide_index=True)

    sel = st.selectbox("Titolo da analizzare", [e["ticker"] for e in entries])
    sel_entry = next((e for e in entries if e["ticker"] == sel), None)

    if sel_entry is not None:
        c1, c2 = st.columns(2)
        if c1.button("✅ Revisionato oggi", key="rev"):
            touch_review(sel)
            st.rerun()
        if c2.button("🗑 Rimuovi dalla watchlist", key="rm"):
            remove_entry(sel)
            st.rerun()

        a = analyses.get(sel)
        if a is None:
            st.warning(f"Dati prezzo non disponibili per {sel}.")
        else:
            df = a["df"]
            price = a["price"]
            bs = a["bs"]
            hc = health_check(sel)

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Prezzo", f"{price:,.2f}")
            m2.metric("Drawdown ATH", f"{bs['drawdown']:.1f}%")
            m3.metric("Health", f"{hc['score']}/100")
            m4.metric("Bottom Score", f"{bs['score']}/100")

            col = COLORS["dark"] if st.session_state.dark_mode else COLORS["light"]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df.index, y=df["Close"], name="Close",
                                     line=dict(color=col["accent"], width=1.5)))
            ylo = float(df["Low"].min()) * 0.97
            yhi = float(df["High"].max()) * 1.03
            for zi, z in enumerate(a["zones"][:3], 1):
                if z["hi"] < ylo or z["lo"] > yhi:
                    continue
                fig.add_hrect(y0=z["lo"], y1=z["hi"], fillcolor=col["warning"],
                              opacity=0.08 + 0.20 * z["score"] / 100,
                              line_width=0, annotation_text=f"Z{zi} ·{z['score']}")
            for an in a["anchors"]:
                if ylo <= an["vwap"] <= yhi:
                    tag = f"{an['label']} {an['date'].strftime('%m/%y')}"
                    if an["near"]:
                        tag += " 📅"
                    fig.add_hline(y=an["vwap"], line_color=col["positive"],
                                  line_dash="dot", annotation_text=tag)
            fig.add_hline(y=a["vwap60"], line_color=col["text_muted"],
                          line_dash="dot", annotation_text="VWAP60")
            levels = sel_entry.get("levels", {})
            for lvl_name, lvl_val in levels.items():
                if lvl_val and lvl_val > 0:
                    fig.add_hline(y=lvl_val, line_color=col["accent"],
                                  line_dash="solid", annotation_text=f"{lvl_name} (👤)")
            fig.update_yaxes(range=[ylo, yhi])
            style_fig(fig, st.session_state.dark_mode, height=420)
            st.plotly_chart(fig, use_container_width=True)

            with st.expander("Livelli manuali (👤)"):
                with st.form("levels_form"):
                    l1 = st.number_input("L1 (supporto forte)", value=levels.get("L1", 0.0), step=0.1)
                    l2 = st.number_input("L2 (supporto medio)", value=levels.get("L2", 0.0), step=0.1)
                    l3 = st.number_input("L3 (resistenza)", value=levels.get("L3", 0.0), step=0.1)
                    submitted = st.form_submit_button("Salva livelli", type="primary")
                    if submitted:
                        update_levels(sel, {"L1": l1, "L2": l2, "L3": l3})
                        st.success("Livelli salvati")
                        st.rerun()

            with st.expander("📅 Trimestrali"):
                es = a["es"]
                if es["positive"] is True:
                    st.success("Ultima trimestrale: positiva (surprise EPS > 0 o ricavi YoY > 0).")
                elif es["positive"] is False:
                    st.warning("Ultima trimestrale: negativa.")
                else:
                    st.caption("Trimestrali: dati non disponibili (n/d).")
                if es["date"]:
                    sur_txt = f"{es['surprise']:+.1f}%" if es["surprise"] is not None else "n/d"
                    st.caption(f"Ultima riportata: {es['date']} · Surprise EPS: {sur_txt}")
                if es["rev_yoy"] is not None:
                    st.caption(f"Ricavi ultimi 12 mesi vs anno prima: {es['rev_yoy']:+.1f}%")
                if es["quarters"] is not None and len(es["quarters"]) >= 2:
                    q = es["quarters"].iloc[-8:]
                    figq = go.Figure(go.Bar(x=[str(c.date()) for c in q.index],
                                            y=q.values / 1e9,
                                            marker_color=col["accent"]))
                    style_fig(figq, st.session_state.dark_mode, height=240)
                    st.plotly_chart(figq, use_container_width=True)
                    st.caption("Ricavi trimestrali, miliardi.")

            with st.expander("Health Check — dettagli"):
                for chk in hc["checks"]:
                    icon = "✅" if chk["ok"] else "❌"
                    st.markdown(f"{icon} **{chk['name']}** — {chk['detail']}")

    with st.expander("🔔 Storico alert"):
        hist = load_alert_state().get("history", [])
        if not hist:
            st.caption("Nessun alert archiviato. (Alert automatici disattivati.)")
        else:
            rows_a = [{"Data": a["ts"][:16].replace("T", " "),
                       "Ticker": a["ticker"], "Tipo": a["kind"],
                       "Prezzo": a["price"]} for a in reversed(hist)]
            st.dataframe(pd.DataFrame(rows_a), use_container_width=True, hide_index=True)

# ── Analisi singola libera ─────────────────────────────────
st.markdown("### Analisi singola")
universe = build_universe()
mode = st.radio("Sorgente", ["Da universo", "Ticker libero"], horizontal=True)
ticker = None
if mode == "Da universo":
    ticker = st.selectbox("Titolo", universe)
else:
    raw = st.text_input("Ticker", value="CPR").strip().upper()
    if raw:
        with st.spinner("Risoluzione ticker…"):
            ticker = resolve_ticker(raw)
        if ticker is None:
            st.error(f"Nessun dato per '{raw}' sulle borse supportate.")
        elif ticker != raw:
            st.caption(f"Risolto come {ticker}")

if ticker:
    try:
        df = get_prices(ticker)
    except Exception as e:
        st.error(f"Dati non disponibili per {ticker}: {e}")
        st.stop()

    a = build_analysis(ticker)
    if a is None:
        st.error(f"Analisi non disponibile per {ticker}.")
        st.stop()

    price = a["price"]
    bs = a["bs"]
    hc = health_check(ticker)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Prezzo", f"{price:,.2f}",
              f"{df['Close'].pct_change().iloc[-1] * 100:+.2f}%")
    c2.metric("Drawdown ATH", f"{bs['drawdown']:.1f}%")
    c3.metric("Health", f"{hc['score']}/100")
    c4.metric("Bottom Score", f"{bs['score']}/100")

    vwa = a["anchors"]
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("RSI(14)", f"{bs['rsi']:.0f}")
    c6.metric("VWAP60", f"{a['vwap60']:,.2f}")
    c7.metric("VWA1", f"{vwa[0]['vwap']:,.2f}" if vwa else "—")
    c8.metric("VWA2", f"{vwa[1]['vwap']:,.2f}" if len(vwa) > 1 else "—")

    col = COLORS["dark"] if st.session_state.dark_mode else COLORS["light"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["Close"], name="Close",
                             line=dict(color=col["accent"], width=1.5)))
    ylo = float(df["Low"].min()) * 0.97
    yhi = float(df["High"].max()) * 1.03
    for zi, z in enumerate(a["zones"][:3], 1):
        if z["hi"] < ylo or z["lo"] > yhi:
            continue
        fig.add_hrect(y0=z["lo"], y1=z["hi"], fillcolor=col["warning"],
                      opacity=0.08 + 0.20 * z["score"] / 100,
                      line_width=0, annotation_text=f"Z{zi} ·{z['score']}")
    for an in a["anchors"]:
        if ylo <= an["vwap"] <= yhi:
            tag = f"{an['label']} {an['date'].strftime('%m/%y')}"
            if an["near"]:
                tag += " 📅"
            fig.add_hline(y=an["vwap"], line_color=col["positive"],
                          line_dash="dot", annotation_text=tag)
    fig.add_hline(y=a["vwap60"], line_color=col["text_muted"],
                  line_dash="dot", annotation_text="VWAP60")
    fig.update_yaxes(range=[ylo, yhi])
    style_fig(fig, st.session_state.dark_mode, height=420)
    st.plotly_chart(fig, use_container_width=True)

    if st.button("➕ Promuovi in watchlist (🤖 auto)", type="primary"):
        add_entry(ticker, origin="auto",
                  poc=a["zones"][0]["center"] if a["zones"] else None)
        st.success(f"{ticker} promosso in watchlist come 🤖")

    with st.expander("📅 Trimestrali"):
        es = a["es"]
        if es["positive"] is True:
            st.success("Ultima trimestrale: positiva.")
        elif es["positive"] is False:
            st.warning("Ultima trimestrale: negativa.")
        else:
            st.caption("Trimestrali: dati non disponibili (n/d).")
        if es["quarters"] is not None and len(es["quarters"]) >= 2:
            q = es["quarters"].iloc[-8:]
            figq = go.Figure(go.Bar(x=[str(c.date()) for c in q.index],
                                    y=q.values / 1e9,
                                    marker_color=col["accent"]))
            style_fig(figq, st.session_state.dark_mode, height=240)
            st.plotly_chart(figq, use_container_width=True)
            st.caption("Ricavi trimestrali, miliardi.")

    with st.expander("Health Check — dettagli"):
        for chk in hc["checks"]:
            icon = "✅" if chk["ok"] else "❌"
            st.markdown(f"{icon} **{chk['name']}** — {chk['detail']}")

    with st.expander("Bottom Score — componenti"):
        for k, v in bs["components"].items():
            st.markdown(f"- **{k}**: {v:.0f}/100")

    # ── Lettura grafico Groq (unica, non critica) ──────────
    with st.expander("📷 Lettura grafico (Groq, opzionale)"):
        up = st.file_uploader("Screenshot grafico (PNG/JPG)",
                              type=["png", "jpg", "jpeg"], key="vision_up")
        if st.button("Leggi grafico", type="primary",
                     disabled=(up is None), key="vision_run"):
            with st.status("Lettura in corso…", expanded=True) as status:
                try:
                    res = read_chart(up.getvalue(), mime=up.type or "image/png")
                    status.update(label=f"Lettura completata ({res['model']})",
                                  state="complete")
                except Exception as e:
                    status.update(label="Motore non disponibile", state="error")
                    st.warning(
                        f"Lettura automatica non disponibile ({e}). "
                        "Si passa alla lettura manuale: zone e VWAP calcolati "
                        "restano a video."
                    )
                    res = None

            if res is not None:
                j = res.get("json")
                if j:
                    v1, v2 = st.columns(2)
                    v1.markdown(f"**Trend breve**: {j.get('trend_breve', 'n/d')}")
                    v1.markdown(f"**Trend medio**: {j.get('trend_medio', 'n/d')}")
                    v2.markdown(f"**Prezzo vs VWAP**: {j.get('prezzo_vs_vwap', 'n/d')}")
                    v2.markdown(f"**Zona volumi**: {j.get('zona_volumi', 'n/d')}")
                    lv = j.get("livelli_chiave") or []
                    if lv:
                        st.markdown("**Livelli chiave**: " + " · ".join(str(x) for x in lv))
                    if j.get("incoerenze"):
                        st.markdown(f"**Incoerenze**: {j['incoerenze']}")
                    st.markdown(f"**Sintesi**: {j.get('sintesi', '')}")
                else:
                    st.code(res["text"])
                st.caption(
                    "Lettura automatica: può contenere errori, soprattutto sui "
                    "prezzi esatti. Le zone del portale restano la fonte di "
                    "verità. Mai usare come ordine."
                )
