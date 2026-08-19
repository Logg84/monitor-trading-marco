"""
Watchlist — home. Tabella 👤/🤖 con POC20y/zone/Δ%/segnale/trimestrali,
flag stale, livelli L1/L2/L3, storico alert, analisi singola,
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
    get_prices, get_prices_long, atr, vwap_anchored, poc_zone,
    poc_zone_from_profile, volume_profile, poc_long_weekly,
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

# ── Analisi per ticker (una sola chiamata get_prices) ──────
def build_analysis(ticker: str) -> dict | None:
    try:
        df = get_prices(ticker)
    except Exception:
        return None
    vwap = vwap_anchored(df)
    price = float(df["Close"].iloc[-1])
    ath = float(df["Close"].max())
    dd = (price / ath - 1) * 100
    a20 = atr(df)
    bs = bottom_score(df, poc=vwap)

    try:
        wdf = get_prices_long(ticker)
        pocL = poc_long_weekly(wdf)
    except Exception:
        pocL = None
    if pocL is None:
        pocL = volume_profile(df)["poc"]
    lo, hi = poc_zone(pocL, a20)
    in_zone = bool(lo <= price <= hi)

    return {
        "df": df, "vwap": vwap, "pocL": pocL, "lo": lo, "hi": hi,
        "in_zone": in_zone, "bs": bs, "price": price, "dd": dd,
        "signal": rebound_signal(dd, bs["decel"], bs["rsi"], in_zone, price <= vwap),
        "es": earnings_snapshot(ticker),
    }

st.markdown("## Watchlist")
st.caption(
    "POC20y: volume profile su storico settimanale lungo. Zona: ±0.6·ATR(20). "
    "Segnale 🟢 = DD≤−20% + decel>0 + RSI<45 + (in zona o ≤VWAP). "
    "Lettura, mai ordine."
)
entries = load_watchlist()

analyses = {}
for e in entries:
    a = build_analysis(e["ticker"])
    if a is not None:
        analyses[e["ticker"]] = a

metrics = {
    t: {"vwap": round(a["vwap"], 4), "poc_auto": round(a["pocL"], 4),
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
        es = a["es"]
        trim = "✅" if es["positive"] is True else ("❌" if es["positive"] is False else "n/d")
        rows.append({
            "Orig.": "👤" if e["origin"] == "manual" else "🤖",
            "Ticker": e["ticker"],
            "Prezzo": round(a["price"], 2),
            "DD%": round(a["dd"], 1),
            "RSI": round(a["bs"]["rsi"], 0),
            "VWAP": f"{e['vwap']:.2f}" if e.get("vwap") else "—",
            "ΔVWAP%": round((a["price"] / a["vwap"] - 1) * 100, 1) if a["vwap"] else None,
            "POC20y": f"{a['pocL']:.2f}",
            "Zona POC": f"{a['lo']:.2f}–{a['hi']:.2f}",
            "ΔPOC%": round((a["price"] / a["pocL"] - 1) * 100, 1) if a["pocL"] else None,
            "In zona": "✅" if a["in_zone"] else "",
            "Segnale": a["signal"],
            "Trim.": trim,
            "Bottom": a["bs"]["score"],
            "Stale": "⚠️" if is_stale(e) else "",
        })

    if rows:
        sc1, sc2 = st.columns([2, 1])
        sort_col = sc1.selectbox(
            "Ordina per",
            ["Bottom", "DD%", "RSI", "Prezzo", "ΔPOC%", "ΔVWAP%", "Ticker"],
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
            pocL, lo, hi = a["pocL"], a["lo"], a["hi"]
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
                          line_width=0, annotation_text="Zona POC20y")
            fig.add_hline(y=pocL, line_color=col["text"], line_dash="dash",
                          annotation_text=f"POC20y {'👤' if sel_entry.get('poc_origin') == 'manual' else '🤖'}")
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
                    figq = go.Figure(go.Bar(
                        x=[str(c.date()) for c in q.index],
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

    price = float(df["Close"].iloc[-1])
    vwap = vwap_anchored(df)
    a20 = atr(df)
    try:
        wdf = get_prices_long(ticker)
        pocL = poc_long_weekly(wdf)
    except Exception:
        pocL = None
    if pocL is None:
        pocL = volume_profile(df)["poc"]
    lo, hi = poc_zone(pocL, a20)
    bs = bottom_score(df, poc=pocL)
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
    c7.metric("POC20y", f"{pocL:,.2f}")
    c8.metric("Zona POC20y", f"{lo:.2f} – {hi:.2f}")

    col = COLORS["dark"] if st.session_state.dark_mode else COLORS["light"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["Close"], name="Close",
                             line=dict(color=col["accent"], width=1.5)))
    fig.add_hrect(y0=lo, y1=hi, fillcolor=col["warning"], opacity=0.15,
                  line_width=0, annotation_text="Zona POC20y")
    fig.add_hline(y=pocL, line_color=col["text_muted"], line_dash="dash",
                  annotation_text="POC20y")
    fig.add_hline(y=vwap, line_color=col["positive"], line_dash="dot",
                  annotation_text="VWAP")
    style_fig(fig, st.session_state.dark_mode, height=420)
    st.plotly_chart(fig, use_container_width=True)

    if st.button("➕ Promuovi in watchlist (🤖 auto)", type="primary"):
        add_entry(ticker, origin="auto", poc=pocL)
        st.success(f"{ticker} promosso in watchlist come 🤖")

    with st.expander("📅 Trimestrali"):
        es = earnings_snapshot(ticker)
        if es["positive"] is True:
            st.success("Ultima trimestrale: positiva.")
        elif es["positive"] is False:
            st.warning("Ultima trimestrale: negativa.")
        else:
            st.caption("Trimestrali: dati non disponibili (n/d).")
        if es["quarters"] is not None and len(es["quarters"]) >= 2:
            q = es["quarters"].iloc[-8:]
            figq = go.Figure(go.Bar(
                x=[str(c.date()) for c in q.index],
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
                        "Si passa alla lettura manuale: i livelli calcolati "
                        "(POC20y, zona, VWAP) restano a video."
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
                    "prezzi esatti. I livelli del portale restano la fonte di "
                    "verità. Mai usare come ordine."
                )
