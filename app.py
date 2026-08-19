"""
Watchlist — home. Pruning automatico (🤖 e 👤), tabella cliccabile con Nome,
link TradingView, zone volumetriche, VWAP ancorati, Segnale 🟡/🟢, trimestrali;
aggiunta manuale con L1/L2/L3; storico alert; analisi singola.
Lettura, mai ordine — non è consulenza.
"""
import streamlit as st
import plotly.graph_objects as go
import pandas as pd

st.set_page_config(page_title="Watchlist", page_icon="📊", layout="wide",
                   initial_sidebar_state="collapsed")

from ui.theme import inject_css, COLORS, style_fig
from ui.nav import render_navbar, sidebar_nav
from core.data_engine import (
    atr, vwap_anchored, company_name, health_check, bottom_score,
    build_universe, resolve_ticker, tradingview_url,
)
from core.reversal import analyze_ticker, prune_watchlist
from core.watchlist_io import (
    load_watchlist, add_entry, remove_entry, touch_review, update_levels,
    is_stale, reconcile,
)
from core.alerts import load_alert_state

if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = True

inject_css(dark=st.session_state.dark_mode)
render_navbar(title="Watchlist")
sidebar_nav()

def zstr(z: dict | None) -> str:
    if z is None:
        return "—"
    return f"{z['lo']:.2f}–{z['hi']:.2f} ·{z['score']}"

def zones_caption(zones: list[dict]) -> None:
    if zones:
        ztxt = " · ".join(
            f"Z{i} {z['lo']:.2f}–{z['hi']:.2f} ·{z['score']}"
            for i, z in enumerate(zones[:3], 1))
        st.caption(f"Zone volumetriche trovate: {ztxt}")
    else:
        st.caption("Zone volumetriche: nessuna mensola significativa sullo storico lungo.")

st.markdown("## Watchlist")
st.caption(
    "Zone volumetriche su settimanale lungo: score = 60% dimensione + 40% recency (half-life 4y); "
    "larghezza max = min(15% range, 8×ATR20). "
    "VWA1-3: VWAP ancorati a minimi strutturali (≥26 sett. apart), bonus se a ±30gg da trimestrale. "
    "Segnale 🟡 = A + punti ≥2 (G da sola basta; B+C insieme bastano) · 🟢 = A + punti ≥5 + D (G pesa doppio). "
    "Uscite automatiche: 🤖 se DD>−20% o punti<2 per 5 chiusure; 👤 se punti<2 e sotto il livello minimo inserito per 5 chiusure. "
    "Clicca una riga della tabella per aprire l'analisi. Lettura, mai ordine."
)

# ── Pruning automatico (🤖 e 👤) ───────────────────────────
removed = prune_watchlist()
for t, motivo in removed:
    st.warning(f"🗑 {t} rimosso automaticamente dalla watchlist: {motivo}.")

entries = load_watchlist()

analyses = {}
for e in entries:
    a = analyze_ticker(e["ticker"])
    if a is not None:
        analyses[e["ticker"]] = a

metrics = {}
for t, a in analyses.items():
    dfx = a["df"]
    price = float(dfx["Close"].iloc[-1])
    ath = float(dfx["Close"].max())
    metrics[t] = {"vwap": round(vwap_anchored(dfx), 4),
                  "poc_auto": round(a["zones"][0]["center"], 4) if a["zones"] else None,
                  "drawdown": (price / ath - 1) * 100}
entries, msgs = reconcile(entries, {k: v for k, v in metrics.items() if v})
for m in msgs:
    st.warning(m)

with st.expander("➕ Aggiungi titolo (👤 manuale)"):
    with st.form("add_form"):
        c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
        new_ticker = c1.text_input("Ticker (es. CPR.MI o CPR)", value="")
        l1 = c2.number_input("L1 (supporto forte)", value=0.0, step=0.1)
        l2 = c3.number_input("L2 (supporto medio)", value=0.0, step=0.1)
        l3 = c4.number_input("L3 (resistenza)", value=0.0, step=0.1)
        submitted = st.form_submit_button("Aggiungi", type="primary")
        if submitted and new_ticker.strip():
            t = resolve_ticker(new_ticker) or new_ticker.strip().upper()
            add_entry(t, origin="manual")
            lv = {}
            if l1 > 0:
                lv["L1"] = l1
            if l2 > 0:
                lv["L2"] = l2
            if l3 > 0:
                lv["L3"] = l3
            if lv:
                update_levels(t, lv)
            st.rerun()
    st.caption("L1/L2/L3 sono i tuoi livelli personali: non entrano nel calcolo di zone/VWAP; vengono disegnati sul grafico e sono reattivi per gli alert.")

if not entries:
    st.info("Watchlist vuota. Aggiungi un titolo o promuovilo dallo Screening.")
else:
    rows = []
    for e in entries:
        a = analyses.get(e["ticker"])
        if a is None:
            continue
        dfx = a["df"]
        rev = a["rev"]
        es = a["es"]
        bs = bottom_score(dfx, zones=a["zones"])
        price = float(dfx["Close"].iloc[-1])
        vwa1 = a["anchors"][0]["vwap"] if a["anchors"] else None
        in_lbl = ""
        for zi, z in enumerate(a["zones"], 1):
            if z["lo"] <= price <= z["hi"]:
                in_lbl = f"Z{zi}"
                break
        trim = "✅" if es["positive"] is True else ("❌" if es["positive"] is False else "n/d")
        rows.append({
            "Orig.": "👤" if e["origin"] == "manual" else "🤖",
            "Ticker": e["ticker"],
            "TV": tradingview_url(e["ticker"]),
            "Nome": company_name(e["ticker"]),
            "Prezzo": round(price, 2),
            "DD%": round(bs["drawdown"], 1),
            "RSI": round(bs["rsi"], 0),
            "VWAP60": round(vwap_anchored(dfx), 2),
            "VWA1": round(vwa1, 2) if vwa1 else "—",
            "VWA2": round(a["anchors"][1]["vwap"], 2) if len(a["anchors"]) > 1 else "—",
            "VWA3": round(a["anchors"][2]["vwap"], 2) if len(a["anchors"]) > 2 else "—",
            "Z1": zstr(a["zones"][0] if a["zones"] else None),
            "Z2": zstr(a["zones"][1] if len(a["zones"]) > 1 else None),
            "In zona": in_lbl,
            "Segnale": f"{rev['kind']} {rev['points']}/6" if rev["kind"] else "—",
            "Trim.": trim,
            "Bottom": bs["score"],
            "Stale": "⚠️" if is_stale(e) else "",
        })

    if rows:
        sc1, sc2 = st.columns([2, 1])
        sort_col = sc1.selectbox(
            "Ordina per",
            ["Bottom", "DD%", "RSI", "Prezzo", "VWA1", "Nome", "Ticker"],
            index=0, key="wl_sort",
        )
        sort_dir = sc2.radio("Direzione", ["Discendente", "Ascendente"],
                             horizontal=True, key="wl_dir")
        df_w = pd.DataFrame(rows).sort_values(
            sort_col, ascending=(sort_dir == "Ascendente")
        ).reset_index(drop=True)

        column_config = {
            "TV": st.column_config.LinkColumn(
                "TV",
                help="Apri il grafico su TradingView (nuova scheda)",
                display_text="📈",
                width="small",
            ),
        }

        ev_w = st.dataframe(df_w, use_container_width=True, hide_index=True,
                            column_config=column_config,
                            on_select="rerun", selection_mode="single-row",
                            key="tbl_watchlist")

        rows_sel = list(ev_w.selection["rows"]) if ev_w is not None and ev_w.selection else []
        prev = st.session_state.get("prevsel_wl")
        if rows_sel != prev:
            st.session_state["prevsel_wl"] = rows_sel
            if rows_sel and rows_sel[0] < len(df_w):
                st.session_state["wl_sel"] = df_w.iloc[rows_sel[0]]["Ticker"]

    entry_tickers = [e["ticker"] for e in entries]
    stored = st.session_state.get("wl_sel")
    sel = stored if stored in entry_tickers else (entry_tickers[0] if entry_tickers else None)
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
            price = float(df["Close"].iloc[-1])
            bs = bottom_score(df, zones=a["zones"])
            hc = a["hc"]
            vwap60 = vwap_anchored(df)

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
            fig.add_hline(y=vwap60, line_color=col["text_muted"],
                          line_dash="dot", annotation_text="VWAP60")
            levels = sel_entry.get("levels", {})
            for lvl_name, lvl_val in levels.items():
                if lvl_val and lvl_val > 0:
                    fig.add_hline(y=lvl_val, line_color=col["accent"],
                                  line_dash="solid", annotation_text=f"{lvl_name} (👤)")
            fig.update_yaxes(range=[ylo, yhi])
            style_fig(fig, st.session_state.dark_mode, height=420)
            st.plotly_chart(fig, use_container_width=True)
            zones_caption(a["zones"])
            st.caption(
                f"Segnale: {a['rev']['kind'] or '—'} {a['rev']['points']}/6 · "
                f"flag B/C/G/D/E = "
                + "/".join("✔" if a["rev"]["flags"][k] else "·" for k in ("B", "C", "G", "D", "E"))
            )

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
            st.caption("Nessun alert archiviato.")
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
    a = analyze_ticker(ticker)
    if a is None:
        st.error(f"Dati non disponibili per {ticker}.")
        st.stop()

    df = a["df"]
    price = float(df["Close"].iloc[-1])
    bs = bottom_score(df, zones=a["zones"])
    hc = a["hc"]
    vwap60 = vwap_anchored(df)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Prezzo", f"{price:,.2f}",
              f"{df['Close'].pct_change().iloc[-1] * 100:+.2f}%")
    c2.metric("Drawdown ATH", f"{bs['drawdown']:.1f}%")
    c3.metric("Health", f"{hc['score']}/100")
    c4.metric("Bottom Score", f"{bs['score']}/100")

    vwa = a["anchors"]
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("RSI(14)", f"{bs['rsi']:.0f}")
    c6.metric("VWAP60", f"{vwap60:,.2f}")
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
    fig.add_hline(y=vwap60, line_color=col["text_muted"],
                  line_dash="dot", annotation_text="VWAP60")
    fig.update_yaxes(range=[ylo, yhi])
    style_fig(fig, st.session_state.dark_mode, height=420)
    st.plotly_chart(fig, use_container_width=True)
    zones_caption(a["zones"])
    st.caption(
        f"Segnale: {a['rev']['kind'] or '—'} {a['rev']['points']}/6 · "
        f"flag B/C/G/D/E = "
        + "/".join("✔" if a["rev"]["flags"][k] else "·" for k in ("B", "C", "G", "D", "E"))
    )

    st.markdown(f"[📈 Apri **{ticker}** su TradingView]({tradingview_url(ticker)})")

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
