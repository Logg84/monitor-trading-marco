"""
Watchlist — home. Pruning automatico (🤖 e 👤), tabella cliccabile con Nome,
link TradingView, zone volumetriche, VWAP ancorati, Segnale 🟡/🟢, trimestrali,
Wyckoff, data target con alert Telegram.
Write-through GitHub + autoguarigione dal repo + guard anti-svuotamento.
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
from core.sectors import (freschezza, note_for, priorita, sector_cell, sector_label,
                          snapshot_and_source, sub_note, valid_key, vento)

from core.reversal import analyze_ticker, prune_watchlist
from core.gh_sync import publish_watchlist
from core.watchlist_io import (
    load_watchlist, load_watchlist_with_restore,
    add_entry, remove_entry, touch_review, update_levels,
    update_target_date, is_stale, reconcile,
)
from core.alerts import load_alert_state

if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = True
if "company_cache" not in st.session_state:
    st.session_state.company_cache = {}

inject_css(dark=st.session_state.dark_mode)
render_navbar(title="Watchlist")
sidebar_nav()

c_refresh, _ = st.columns([1, 5])
if c_refresh.button("🔄 Aggiorna dati watchlist", type="secondary"):
    st.cache_data.clear()
    st.rerun()

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

def sector_detail(sr: dict | None, key: str | None, sub_key: str | None = None) -> None:
    """Tabella di contesto settore (usata sia in watchlist sia in analisi
    singola): lettura, nessuna decisione. sr=None → 'n/d' dichiarato, mai 50
    inventato o 'neutro' di default."""
    if sr is None:
        st.caption(f"Settore {sector_label(key)}: stato non disponibile (n/d) — "
                   "né live né cache del repo. 'n/d' non significa 'neutro'.")
        return
    st.dataframe(pd.DataFrame([
        {"Metrica": "Settore", "Valore": sr["label"]},
        {"Metrica": "Livello", "Valore": sr.get("livello") or "settore GICS"},
        {"Metrica": "Gamba capitalizzazione (CW)", "Valore": sr["cw"]},
        {"Metrica": "Gamba pesi uguali (EW)", "Valore": sr.get("ew") or "—"},
        {"Metrica": "Chi tira il settore", "Valore": sr.get("guida") or "n/d"},
        {"Metrica": "Δ EW−CW 1m / 3m / 6m",
         "Valore": " / ".join("n/d" if sr.get(k) is None else f"{sr[k]:+.1f} pt"
                              for k in ("spread21", "spread63", "spread126"))},
        {"Metrica": "Stato", "Valore": f"{sr['emoji']} {sr['stato']} · {sr['score']}/100"},
        {"Metrica": "Direzione", "Valore": sr["dir"]},
        {"Metrica": "Momentum 1m / 3m / 6m",
         "Valore": " / ".join("n/d" if sr.get(k) is None else f"{sr[k]:+.1f}%"
                              for k in ("mom21", "mom63", "mom126"))},
        {"Metrica": "Forza relativa 3m vs benchmark",
         "Valore": "n/d" if sr.get("rs63") is None else f"{sr['rs63']:+.1f} pt"},
        {"Metrica": "Vantaggio EW persistente",
         "Valore": ("n/d" if sr.get("consistenza") is None
                    else f"{sr['consistenza']:.0f}% sedute su 63 · "
                         + f"{abs(sr.get('streak') or 0)} sedute di fila "
                           f"({'a favore EW' if (sr.get('streak') or 0) > 0 else 'a favore CW'})")},
        {"Metrica": "Posizione range 52 sett.",
         "Valore": "n/d" if sr.get("pos52") is None else f"{sr['pos52']:.0f}%"},
        {"Metrica": "Sopra SMA50 / SMA200 (gamba cw)",
         "Valore": f"{'sì' if sr.get('above50') else 'no'} / "
                   f"{'sì' if sr.get('above200') else 'no'}"},
    ]), use_container_width=True, hide_index=True)
    if sr.get("note"):
        st.caption(sr["note"])
    if sr.get("ew_note"):
        st.caption(f"Gamba equal-weighted: {sr['ew_note']}")
    st.caption("Il settore è contesto: non aggiunge né toglie punti al segnale "
               "🟡/🟢 e non partecipa al pruning. Dettagli nel pannello Settori.")

def cname(ticker: str) -> str:
    if ticker not in st.session_state.company_cache:
        st.session_state.company_cache[ticker] = company_name(ticker)
    return st.session_state.company_cache[ticker]

st.markdown("## Watchlist")
st.caption(
    "Zone volumetriche su settimanale lungo: score = 60% dimensione + 40% recency (half-life 4y); "
    "larghezza max = min(15% range, 8×ATR20). "
    "VWA1-3: VWAP ancorati a minimi strutturali (≥26 sett. apart), bonus se a ±30gg da trimestrale. "
    "Segnale 🟡 = A + punti ≥2 (G da sola basta; B+C insieme bastano) · 🟢 = A + punti ≥5 + D (G pesa doppio). "
    "Wyckoff: rilevamento pattern accumulazione SC→AR→ST→Spring→SOS→LPS, punteggio 1-10. "
    "Uscite automatiche: 🤖 se DD>−20% o punti<2 per 5 chiusure; 👤 se punti<2 e sotto il livello minimo inserito per 5 chiusure. "
    "Contesto di settore (ETF capitalization-weighted + equal-weighted): stato 0-100 del settore di ogni titolo, nota ⚠️ se il segnale è su un settore in calo, "
    "e Priorità = Bottom + bonus settore (±10) per ordinare: il settore NON modifica i punti 🟡/🟢 né le uscite. "
    "Clicca una riga della tabella per aprire l'analisi. Lettura, mai ordine."
)

# ── Caricamento con autoguarigione dal repo ────────────────
entries = load_watchlist_with_restore()
if entries and not load_watchlist():
    st.caption("Watchlist ripristinata da GitHub (fonte di verità).")

# ── Contesto di settore (ETF cap-w + equal-w): lettura, non regola ──────
_snap, ssrc = snapshot_and_source()
srows = {k: v for k, v in (_snap or {}).get("rows", {}).items()
         if v.get("livello") == "settore"}
subrows = {k: v for k, v in (_snap or {}).get("rows", {}).items()
           if v.get("livello") != "settore"}

def valid_sub(k):
    """Chiave di sotto-settore utilizzabile (vedi valid_key per i settori)."""
    return k if k in subrows else None

def sub_label_str(k):
    return subrows[k]["label"] if k in subrows else "—"
st.caption(f"Contesto settori ({len(srows)} GICS + {len(subrows)} sotto-settori/temi): "
           f"{freschezza(_snap, ssrc == 'live')}. Il settore è lettura di contesto: "
           "non modifica i punti 🟡/🟢 né le uscite.")


# ── SINGOLO PASSO di analisi per pruning + display ─────────
analyses = {}
if entries:
    prog = st.progress(0.0, text=f"Analisi watchlist: 0/{len(entries)} titoli…")
    for i, e in enumerate(entries, start=1):
        a = analyze_ticker(e["ticker"])
        if a is not None:
            analyses[e["ticker"]] = a
        prog.progress(i / len(entries),
                      text=f"Analisi watchlist: {i}/{len(entries)} titoli ({e['ticker']})…")
    prog.empty()

# ── Pruning usando le analisi già calcolate ─────────────────
removed = prune_watchlist(analyses=analyses if analyses else None)
for t, motivo in removed:
    st.warning(f"🗑 {t} rimosso automaticamente dalla watchlist: {motivo}.")
if removed:
    # Fondamentale: prune_watchlist ha già scritto su disco il file senza
    # le entry rimosse. Se non ricarichiamo qui, 'entries' resta la copia
    # in memoria di PRIMA del pruning (con i ticker rimossi ancora dentro),
    # e reconcile() più sotto la risalverebbe così com'è, rimettendo
    # nel file esattamente i ticker appena tolti.
    entries = load_watchlist()

metrics = {}
for t, a in analyses.items():
    dfx = a["df"]
    price = float(dfx["Close"].iloc[-1])
    ath = float(dfx["Close"].max())
    metrics[t] = {"vwap": round(vwap_anchored(dfx), 4),
                  "poc_auto": round(a["zones"][0]["center"], 4) if a["zones"] else None,
                  "drawdown": (price / ath - 1) * 100,
                  "sector": valid_key(a.get("sector")), "sub": a.get("sub")}

n_before = len(entries)
entries, msgs = reconcile(entries, {k: v for k, v in metrics.items() if v})
for m in msgs:
    st.warning(m)
if msgs:
    if len(entries) > 0:
        publish_watchlist()
    else:
        st.error(
            f"Reconcile avrebbe svuotato la watchlist ({n_before} → 0): "
            "pubblicazione su GitHub bloccata (circuito di protezione).")

with st.expander("➕ Aggiungi titolo (👤 manuale)"):
    with st.form("add_form"):
        c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
        new_ticker = c1.text_input("Ticker (es. CPR.MI o CPR)", value="")
        l1 = c2.number_input("L1 (supporto forte)", value=0.0, step=0.1)
        l2 = c3.number_input("L2 (supporto medio)", value=0.0, step=0.1)
        l3 = c4.number_input("L3 (resistenza)", value=0.0, step=0.1)
        td_str = c5.date_input("Data target (alert)", value=None)
        submitted = st.form_submit_button("Aggiungi", type="primary")
        if submitted and new_ticker.strip():
            t = resolve_ticker(new_ticker) or new_ticker.strip().upper()
            td_iso = td_str.isoformat() if td_str else None
            add_entry(t, origin="manual", target_date=td_iso)
            lv = {}
            if l1 > 0:
                lv["L1"] = l1
            if l2 > 0:
                lv["L2"] = l2
            if l3 > 0:
                lv["L3"] = l3
            if lv:
                update_levels(t, lv)
            publish_watchlist()
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
        wyk = a["wyckoff"]
        bs = bottom_score(dfx, zones=a["zones"])
        price = float(dfx["Close"].iloc[-1])
        vwa1 = a["anchors"][0]["vwap"] if a["anchors"] else None
        in_lbl = ""
        for zi, z in enumerate(a["zones"], 1):
            if z["lo"] <= price <= z["hi"]:
                in_lbl = f"Z{zi}"
                break
        trim = "✅" if es["positive"] is True else ("❌" if es["positive"] is False else "n/d")
        wyk_str = f"{wyk['score_10']}/10" if wyk["n_events"] >= 2 else "—"
        sec_key = a.get("sector") or valid_key(e.get("sector"))
        sub_key = a.get("sub") or valid_sub(e.get("sub"))
        sec_score = (srows.get(sec_key) or {}).get("score") if sec_key else None
        sec_vento = vento(sec_key, srows)
        contro = bool(rev["kind"] and sec_vento == "contro")
        sec_lbl = sector_label(sec_key)
        if contro and sec_lbl != "—":
            sec_lbl = f"⚠️ {sec_lbl}"
        levels_e = e.get("levels", {}) or {}
        td_raw = e.get("target_date")
        td_fmt = "—"
        if td_raw:
            try:
                from datetime import date as _date
                td_fmt = _date.fromisoformat(td_raw).strftime("%d/%m/%y")
            except Exception:
                td_fmt = td_raw
        rows.append({
            "Orig.": "👤" if e["origin"] == "manual" else "🤖",
            "Ticker": e["ticker"],
            "TV": tradingview_url(e["ticker"]),
            "Nome": cname(e["ticker"]),
            "Settore": sec_lbl,
            "Sotto": sub_label_str(sub_key),
            "SottoΔ": ((subrows.get(sub_key) or {}).get("d63") if sub_key else None),
            "Sector": sector_cell(sec_key, srows),
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
            "Wyckoff": wyk_str,
            "Trim.": trim,
            "Bottom": bs["score"],
            "Priorità": priorita(bs["score"], sec_score),
            "L1": levels_e.get("L1") or "—",
            "L2": levels_e.get("L2") or "—",
            "L3": levels_e.get("L3") or "—",
            "🎯 Alert": td_fmt,
            "👁️ Da rivedere": "⚠️" if is_stale(e) else "",
        })

    if rows:
        sc1, sc2 = st.columns([2, 1])
        sort_col = sc1.selectbox(
            "Ordina per",
            ["Bottom", "Priorità", "DD%", "RSI", "Prezzo", "VWA1", "Wyckoff",
             "Settore", "Sotto", "Sector", "Nome", "Ticker"],
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
            "Settore": st.column_config.TextColumn(
                "Settore",
                help="Settore del titolo (classificazione da settore/"
                     "industria di mercato). ⚠️ = segnale attivo su settore in "
                     "calo: è una nota di prudenza, il segnale resta valido."),
            "Sector": st.column_config.TextColumn(
                "Sector",
                help="Stato del settore: emoji (FORTE / IN MIGLIORAMENTO / "
                     "NEUTRO / DEBOLE / IN CALO) + freccia di direzione + "
                     "punteggio 0-100 (trend, momentum 3/6m, forza relativa vs "
                     "SPY, posizione su 52 sett., breadth EW−CW). Contesto, mai "
                     "regola di ingresso."),
            "Priorità": st.column_config.NumberColumn(
                "Priorità",
                help="Bottom Score + bonus di settore (±10 = (stato−50)/5). "
                     "Serve a ORDINARE la lista, non a decidere l'ingresso.",
                format="%d"),
            "L1": st.column_config.TextColumn(
                "L1", help="Livello manuale L1 (supporto forte) — impostato da te sotto la tabella"),
            "L2": st.column_config.TextColumn(
                "L2", help="Livello manuale L2 (supporto medio)"),
            "L3": st.column_config.TextColumn(
                "L3", help="Livello manuale L3 (resistenza)"),
            "🎯 Alert": st.column_config.TextColumn(
                "🎯 Alert", help="Data target: se raggiunta, invia un alert Telegram"),
            "👁️ Da rivedere": st.column_config.TextColumn(
                "👁️ Da rivedere",
                help="⚠️ = entry manuale non revisionata da più di 4 mesi"),
        }

        ev_w = st.dataframe(df_w, use_container_width=True, hide_index=True,
                            column_config=column_config,
                            on_select="rerun", selection_mode="single-row",
                            key="tbl_watchlist")
        st.caption(
            "👁️ Da rivedere: compare solo sulle entry 👤 manuali non "
            "revisionate (pulsante ✅ sotto) da più di 4 mesi. "
            "🎯 Alert: data target che, se raggiunta, invia un alert Telegram."
        )

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
        levels = sel_entry.get("levels", {}) or {}
        c1, c2 = st.columns(2)
        if c1.button("✅ Revisionato oggi", key="rev"):
            touch_review(sel)
            publish_watchlist()
            st.rerun()
        if c2.button("🗑 Rimuovi dalla watchlist", key="rm"):
            remove_entry(sel)
            publish_watchlist()
            st.rerun()

        with st.expander(f"✏️ Modifica livelli e alert — {sel}", expanded=True):
            with st.form("levels_form"):
                l1 = st.number_input("L1 (supporto forte)", value=levels.get("L1", 0.0), step=0.1)
                l2 = st.number_input("L2 (supporto medio)", value=levels.get("L2", 0.0), step=0.1)
                l3 = st.number_input("L3 (resistenza)", value=levels.get("L3", 0.0), step=0.1)
                cur_td = sel_entry.get("target_date")
                try:
                    from datetime import date
                    td_default = date.fromisoformat(cur_td) if cur_td else None
                except Exception:
                    td_default = None
                td_pick = st.date_input("Data target (alert Telegram)", value=td_default)
                submitted = st.form_submit_button("Salva", type="primary")
                if submitted:
                    update_levels(sel, {"L1": l1, "L2": l2, "L3": l3})
                    td_iso = td_pick.isoformat() if td_pick else None
                    update_target_date(sel, td_iso)
                    publish_watchlist()
                    st.success("Livelli e data target salvati")
                    st.rerun()

        a = analyses.get(sel)
        if a is None:
            st.warning(f"Dati prezzo non disponibili per {sel}.")
        else:
            df = a["df"]
            price = float(df["Close"].iloc[-1])
            bs = bottom_score(df, zones=a["zones"])
            hc = a["hc"]
            wyk = a["wyckoff"]
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
            for lvl_name, lvl_val in levels.items():
                if lvl_val and lvl_val > 0:
                    fig.add_hline(y=lvl_val, line_color=col["accent"],
                                  line_dash="solid", annotation_text=f"{lvl_name} (👤)")
            fig.update_yaxes(range=[ylo, yhi])
            style_fig(fig, st.session_state.dark_mode, height=420)
            st.plotly_chart(fig, use_container_width=True)
            zones_caption(a["zones"])
            sec_note = note_for(a.get("sector"), srows)
            sotto_note = sub_note(a.get("sub"), subrows)
            st.caption(
                f"Segnale: {a['rev']['kind'] or '—'} {a['rev']['points']}/6 · "
                f"flag B/C/G/D/E = "
                + "/".join("✔" if a["rev"]["flags"][k] else "·" for k in ("B", "C", "G", "D", "E"))
                + f" · Wyckoff {wyk['score_10']}/10 ({wyk['confidence']})"
                + (f" — {'+'.join(wyk['events'])}" if wyk["events"] else "")
            )
            # Contesto di settore: è una RIGA IN PIÙ, non un filtro — il segnale
            # 🟡/🟢 resta quello di reversal_state. ⚠️ quando c'è un segnale su
            # un settore che sta scendendo (lettura prudente, non blocco).
            if sec_note:
                if a["rev"]["kind"] and vento(a.get("sector"), srows) == "contro":
                    st.warning(f"⚠️ {sec_note}")
                else:
                    st.caption(sec_note)
            if sotto_note:
                st.caption(sotto_note)

            with st.expander("🏭 Contesto di settore (ETF cap-w + equal-w)"):
                sec_k_det = a.get("sector") or valid_key(sel_entry.get("sector"))
                sector_detail((srows or {}).get(sec_k_det or ""), sec_k_det)

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

            with st.expander("🔬 Wyckoff — dettagli"):
                if wyk["n_events"] < 2:
                    st.caption("Pattern di accumulazione Wyckoff non riconosciuto.")
                else:
                    st.markdown(f"**Punteggio**: {wyk['score_10']}/10 · Confidenza: {wyk['confidence']}")
                    st.markdown(f"**Eventi rilevati**: {' → '.join(wyk['events'])}")
                    for ev, det in wyk["details"].items():
                        parts = [f"**{ev}**: "]
                        for k, v in det.items():
                            parts.append(f"{k}={v}")
                        st.caption(" | ".join(parts))
                    if wyk["poc_bonus"]:
                        st.success("✅ Conferma incrociata con POC volumetrico: bonus attivo.")

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
    wyk = a["wyckoff"]
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
        + f" · Wyckoff {wyk['score_10']}/10 ({wyk['confidence']})"
        + (f" — {'+'.join(wyk['events'])}" if wyk["events"] else "")
    )

    st.markdown(f"[📈 Apri **{ticker}** su TradingView]({tradingview_url(ticker)})")

    # ── Contesto di settore nell'analisi singola ───────────
    sec_k = valid_key(a.get("sector"))
    sec_r = (srows or {}).get(sec_k or "")
    st.metric("Settore / stato",
              f"{sector_label(sec_k)}",
              f"{sec_r['emoji']} {sec_r['score']}/100 {sec_r['dir']}"
              if sec_r and sec_r.get("score") is not None else "n/d",
              delta_color="off")
    _note = note_for(sec_k, srows)
    if sub_note(a.get("sub"), subrows):
        st.caption(sub_note(a.get("sub"), subrows))
    if _note:
        if a["rev"]["kind"] and vento(sec_k, srows) == "contro":
            st.warning(f"⚠️ {_note}")
        else:
            st.caption(_note)
    with st.expander("🏭 Contesto di settore (ETF cap-w + equal-w)"):
        sector_detail(sec_r, sec_k)

    if st.button("➕ Promuovi in watchlist (👤 manuale)", type="primary"):
        add_entry(ticker, origin="manual",
                  poc=a["zones"][0]["center"] if a["zones"] else None)
        publish_watchlist()
        st.success(f"{ticker} promosso in watchlist come 👤")

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

    with st.expander("🔬 Wyckoff — dettagli"):
        if wyk["n_events"] < 2:
            st.caption("Pattern di accumulazione Wyckoff non riconosciuto.")
        else:
            st.markdown(f"**Punteggio**: {wyk['score_10']}/10 · Confidenza: {wyk['confidence']}")
            st.markdown(f"**Eventi rilevati**: {' → '.join(wyk['events'])}")
            for ev, det in wyk["details"].items():
                parts = [f"**{ev}**: "]
                for k, v in det.items():
                    parts.append(f"{k}={v}")
                st.caption(" | ".join(parts))
            if wyk["poc_bonus"]:
                st.success("✅ Conferma incrociata con POC volumetrico: bonus attivo.")
