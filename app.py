"""
Watchlist — home. Tabella 👤/🤖, flag stale, livelli L1/L2/L3,
storico alert, analisi singola.
"""
import streamlit as st
import plotly.graph_objects as go
import pandas as pd

st.set_page_config(page_title="Watchlist", page_icon="📊", layout="wide",
                   initial_sidebar_state="collapsed")

from ui.theme import inject_css, COLORS, style_fig
from ui.nav import render_navbar, sidebar_nav
from core.data_engine import (
    get_prices, vwap_anchored, poc_zone_from_profile,
    health_check, bottom_score, build_universe, resolve_ticker,
)
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

# ── Analisi per ticker (una sola chiamata get_prices) ──────
def build_analysis(ticker: str) -> dict | None:
    try:
        df = get_prices(ticker)
    except Exception:
        return None
    vwap = vwap_anchored(df)
    poc, lo, hi = poc_zone_from_profile(df)
    bs = bottom_score(df, poc=poc)
    price = float(df["Close"].iloc[-1])
    ath = float(df["Close"].max())
    return {
        "df": df, "vwap": vwap, "poc": poc, "lo": lo, "hi": hi,
        "bs": bs, "price": price, "dd": (price / ath - 1) * 100,
    }

st.markdown("## Watchlist")
entries = load_watchlist()

analyses = {}
for e in entries:
    a = build_analysis(e["ticker"])
    if a is not None:
        analyses[e["ticker"]] = a

metrics = {
    t: {"vwap": round(a["vwap"], 4), "poc_auto": round(a["poc"], 4),
        "drawdown": a["dd"]}
    for t, a in analyses.items()
}
entries, msgs = reconcile(entries, metrics)
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
        rows.append({
            "Orig.": "👤" if e["origin"] == "manual" else "🤖",
            "Ticker": e["ticker"],
            "Prezzo": round(a["price"], 2),
            "DD%": round(a["dd"], 1),
            "RSI": round(a["bs"]["rsi"], 0),
            "VWAP": f"{e['vwap']:.2f}" if e.get("vwap") else "—",
            "POC": f"{a['poc']:.2f}",
            "Zona POC": f"{a['lo']:.2f}–{a['hi']:.2f}",
            "Bottom": a["bs"]["score"],
            "Stale": "⚠️" if is_stale(e) else "",
        })

    if rows:
        sc1, sc2 = st.columns([2, 1])
        sort_col = sc1.selectbox(
            "Ordina per",
            ["Bottom", "DD%", "RSI", "Prezzo", "Ticker"],
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
            poc, lo, hi = a["poc"], a["lo"], a["hi"]
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
            fig.add_hrect(y0=lo, y1=hi, fillcolor=col["warning"], opacity=0.15,
                          line_width=0, annotation_text="Zona POC (volume profile)")
            fig.add_hline(y=poc, line_color=col["text"], line_dash="dash",
                          annotation_text=f"POC {'👤' if sel_entry.get('poc_origin') == 'manual' else '🤖'}")
            if sel_entry.get("vwap"):
                fig.add_hline(y=sel_entry["vwap"], line_color=col["positive"],
                              line_dash="dot", annotation_text="VWAP")
            levels = sel_entry.get("levels", {})
            for lvl_name, lvl_val in levels.items():
                if lvl_val and lvl_val > 0:
                    fig.add_hline(y=lvl_val, line_color=col["accent"], line_dash="solid",
                                  annotation_text=f"{lvl_name} (👤)")
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

    price = float(df["Close"].iloc[-1])
    poc, lo, hi = poc_zone_from_profile(df)
    vwap = vwap_anchored(df)
    bs = bottom_score(df, poc=poc)
    hc = health_check(ticker)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Prezzo", f"{price:,.2f}",
              f"{df['Close'].pct_change().iloc[-1] * 100:+.2f}%")
    c2.metric("Drawdown ATH", f"{bs['drawdown']:.1f}%")
    c3.metric("Health", f"{hc['score']}/100")
    c4.metric("Bottom Score", f"{bs['score']}/100")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("RSI(14)", f"{bs['rsi']:.0f}")
    c6.metric("VWAP(60)", f"{vwap:,.2f}")
    c7.metric("POC (volume profile)", f"{poc:,.2f}")
    c8.metric("Zona POC", f"{lo:.2f} – {hi:.2f}")

    col = COLORS["dark"] if st.session_state.dark_mode else COLORS["light"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["Close"], name="Close",
                             line=dict(color=col["accent"], width=1.5)))
    fig.add_hrect(y0=lo, y1=hi, fillcolor=col["warning"], opacity=0.15,
                  line_width=0, annotation_text="Zona POC")
    fig.add_hline(y=poc, line_color=col["text_muted"], line_dash="dash",
                  annotation_text="POC")
    fig.add_hline(y=vwap, line_color=col["positive"], line_dash="dot",
                  annotation_text="VWAP")
    style_fig(fig, st.session_state.dark_mode, height=420)
    st.plotly_chart(fig, use_container_width=True)

    if st.button("➕ Promuovi in watchlist (🤖 auto)", type="primary"):
        add_entry(ticker, origin="auto", poc=poc)
        st.success(f"{ticker} promosso in watchlist come 🤖")

    with st.expander("Health Check — dettagli"):
        for chk in hc["checks"]:
            icon = "✅" if chk["ok"] else "❌"
            st.markdown(f"{icon} **{chk['name']}** — {chk['detail']}")

    with st.expander("Bottom Score — componenti"):
        for k, v in bs["components"].items():
            st.markdown(f"- **{k}**: {v:.0f}/100")
