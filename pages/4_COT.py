"""
COT — Forex & materie prime: matrice forza relativa FX, letture
Producer/Managed/Swap con regola producer estremo, storico merge,
reset storico, diagnostica zip, publish GitHub opzionale.
"""
import datetime

import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="COT", page_icon="🛢️", layout="wide")

from ui.theme import inject_css, COLORS
from ui.nav import render_navbar, sidebar_nav
from core import cot as C

if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = True

inject_css(dark=st.session_state.dark_mode)
render_navbar(title="COT")
sidebar_nav()

c_refresh, _ = st.columns([1, 5])
if c_refresh.button("🔄 Ricarica dati COT", type="secondary"):
    st.cache_data.clear()
    st.rerun()

col = COLORS["dark"] if st.session_state.dark_mode else COLORS["light"]

def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha:.3f})"

TONE_COLOR = {"green": col["positive"], "red": col["negative"],
              "yellow": col["warning"], "ice": col["accent"],
              "muted": col["text_muted"]}

@st.cache_data(ttl=43200, show_spinner=False)
def prezzo_yf(sym: str | None):
    if not sym:
        return None
    try:
        h = yf.download(sym, period="3y", interval="1d",
                        progress=False, auto_adjust=True)
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

st.markdown("## COT — Commitments of Traders")
st.caption("Forex · materie prime · regola producer estremo. Lettura, mai ordine.")

DATA = C.load_cot_data()

# ── Pannello aggiornamento ─────────────────────────────────
anno = datetime.date.today().year
with st.expander("📥 Aggiornamento manuale (download + upload zip)",
                 expanded=(DATA is None)):
    st.markdown(
        f"1️⃣ Scarica i zip annuali Excel dal sito CFTC:\n\n"
        f"- [fut_disagg_xls_{anno}.zip](https://www.cftc.gov/files/dea/history/fut_disagg_xls_{anno}.zip) — materie prime (Producer/Managed/Swap)\n"
        f"- [fut_disagg_xls_{anno-1}.zip](https://www.cftc.gov/files/dea/history/fut_disagg_xls_{anno-1}.zip) — anno precedente (storico)\n"
        f"- [dea_fut_xls_{anno}.zip](https://www.cftc.gov/files/dea/history/dea_fut_xls_{anno}.zip) — tutti i mercati, incl. FX (Legacy)\n"
        f"- [dea_fut_xls_{anno-1}.zip](https://www.cftc.gov/files/dea/history/dea_fut_xls_{anno-1}.zip) — anno precedente (storico)\n\n"
        f"2️⃣ Caricali qui (anche più di uno) e premi Processa. Lo storico esistente viene conservato."
    )
    uploaded = st.file_uploader("Zip CFTC (.zip)", type=["zip"],
                                accept_multiple_files=True,
                                label_visibility="collapsed")
    reset = st.checkbox("🧨 **Riparti da zero** — ignora lo storico salvato e ricostruisce pulito "
                        "(usalo UNA volta dopo un'elaborazione sbagliata)", value=False)
    if st.button("⚙️ Processa e salva", type="primary", disabled=(not uploaded)):
        with st.spinner("Lettura zip + merge con storico…"):
            try:
                payload = C.processa_e_salva([(up.name, up.read()) for up in uploaded],
                                             reset=reset)
                st.cache_data.clear()
                st.success(f"✅ COT salvato: report {payload['meta']['date']} · "
                           f"{payload['meta']['weeks']} settimane · {payload['meta']['rec']} record. "
                           f"Commit e push di data/cot/cot_data.json per sincronizzare gli altri PC.")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Elaborazione fallita: {e}")

# ── Diagnostica ────────────────────────────────────────────
diag = C.load_diag()
if diag and (DATA is None or DATA["meta"]["weeks"] < C.MINW):
    with st.expander("🔬 Diagnostica ultimo Processa (apri e fai screenshot se non funziona)",
                     expanded=True):
        for d in diag:
            st.markdown(f"**{d.get('file')}**")
            st.json(d, expanded=False)

if not DATA:
    st.stop()

META, FX, COMM = DATA["meta"], DATA["fx"], DATA["comm"]
COMM_NAME = DATA.get("comm_name", {})
FX_ORDER = DATA.get("fx_order", [])
COMM_ORDER = DATA.get("comm_order", [])

try:
    d_rep = datetime.date.fromisoformat(META["date"])
    giorni = (datetime.date.today() - d_rep).days
    if giorni > 12:
        st.warning(f"⚠️ Dati COT del {META['date']} ({giorni} giorni fa): "
                   f"il report esce il venerdì, usa 📥 Aggiornamento manuale.")
except Exception:
    pass

st.caption(f"report_date **{META['date']}** · window **{META['weeks']}** sett. · "
           f"records **{META['rec']}** · generato {META['gen']} · {META['src']}")

tab_fx, tab_cm = st.tabs(["💱 Forex · forza relativa", "🛢️ Materie prime · tre categorie"])

# ══════════════════════════════════════════════════════════
with tab_fx:
    syms = [s for s in FX_ORDER if len(FX.get(s) or []) >= C.MINW]
    if not syms:
        st.info("Nessun dato Forex valido: servono ≥ 52 settimane (usa 📥 Aggiornamento).")
    else:
        P, D, D4, D8, Z = {}, {}, {}, {}, {}
        for s in syms:
            v = C.series(FX[s], "nc")
            P[s] = C.percentile(v, v[-1])
            D[s] = C.deriv(v)
            D4[s] = C.deriv(v, w=4)
            D8[s] = C.deriv(v, w=8)
            Z[s] = C.zscore(v)

        # ── Divergenza prezzo/posizionamento ────────────────
        from core.data_engine import get_prices as _get_fx_price
        fx_divergence = {}
        fx_prices = {}
        yf_fx_map = {
            "EUR": "EURUSD=X", "GBP": "GBPUSD=X", "JPY": "USDJPY=X",
            "AUD": "AUDUSD=X", "CAD": "USDCAD=X", "CHF": "USDCHF=X",
            "NZD": "NZDUSD=X",
        }
        for s in syms:
            fx_sym = yf_fx_map.get(s)
            if fx_sym:
                try:
                    px = _get_fx_price(fx_sym, period="1y")
                    if px is not None and len(px) > 20:
                        close_series = px["Close"]
                        pct_chg_4w = (float(close_series.iloc[-1]) /
                                      float(close_series.iloc[-20]) - 1) * 100
                        fx_divergence[s] = {
                            "price_4w": pct_chg_4w,
                            "pos_4w": D4[s],
                            "divergent": (pct_chg_4w > 2 and D4[s] < -5) or (pct_chg_4w < -2 and D4[s] > 5),
                        }
                        fx_prices[s] = close_series
                except Exception:
                    pass

        # ── Layout a due colonne: matrice + ranking + dettaglio ──
        col_fx1, col_fx2 = st.columns([1.5, 1], gap="medium")

        with col_fx1:
            st.markdown("**Matrice forza relativa** — cella = P(riga) − P(colonna) "
                        "su net speculativo. Hover per il verso della coppia.")
            scale = [
                [0.0, col["negative"]],
                [0.35, _rgba(col["negative"], 0.45)],
                [0.5, col["surface"]],
                [0.65, _rgba(col["positive"], 0.45)],
                [1.0, col["positive"]],
            ]
            z_mat, txt_mat, cust_mat = [], [], []
            maxD, maxPair, maxSign = 0, "", 1
            for rs in syms:
                zr, tr, cr = [], [], []
                for cs in syms:
                    if rs == cs:
                        zr.append(None); tr.append("·"); cr.append("—")
                    else:
                        diff = P[rs] - P[cs]
                        if abs(diff) > maxD:
                            maxD, maxPair, maxSign = abs(diff), f"{rs}/{cs}", (1 if diff >= 0 else -1)
                        zr.append(diff); tr.append(f"{diff:+.0f}")
                        verso = "LONG" if diff >= 0 else "SHORT"
                        cr.append(f"<b>{verso} {rs}/{cs}</b> · Δperc {diff:+.0f} · "
                                  f"{rs} {P[rs]:.0f}° vs {cs} {P[cs]:.0f}° · deriv {D[rs]:+.0f}")
                z_mat.append(zr); txt_mat.append(tr); cust_mat.append(cr)

            n = len(syms)
            fig = go.Figure(go.Heatmap(
                z=z_mat, x=syms, y=syms, text=txt_mat, texttemplate="%{text}",
                textfont={"size": 14, "family": "JetBrains Mono",
                          "color": col["text"]},
                customdata=cust_mat, hovertemplate="%{customdata}<extra></extra>",
                zmin=-100, zmax=100, xgap=4, ygap=4,
                colorscale=scale, showscale=False))
            fig.update_layout(
                template="plotly_dark" if st.session_state.dark_mode else "plotly_white",
                height=max(300, n * 54 + 80),
                margin=dict(l=6, r=6, t=6, b=6),
                paper_bgcolor=col["surface"], plot_bgcolor=col["surface"],
                xaxis={"side": "top", "tickfont": {"family": "JetBrains Mono",
                       "size": 12, "color": col["accent"]}},
                yaxis={"autorange": "reversed", "tickfont": {"family": "JetBrains Mono",
                       "size": 12, "color": col["accent"]}})
            st.plotly_chart(fig, use_container_width=True)
            st.markdown(f"Coppia più sbilanciata: **{'LONG' if maxSign > 0 else 'SHORT'} "
                        f"{maxPair}** · Δperc {maxD:.0f}° · soglie alert ±80°")

        with col_fx2:
            st.markdown("**Ranking valute** — percentile del net speculativo. "
                        "Destra = euforia long, sinistra = panico short.")
            order = sorted(syms, key=lambda s: P[s], reverse=True)
            figr = go.Figure(go.Bar(
                y=order, x=[P[s] - 50 for s in order], orientation="h",
                marker={"color": [col["positive"] if P[s] >= 60 else
                                  (col["negative"] if P[s] <= 40 else col["warning"])
                                  for s in order]},
                text=[f"{P[s]:.0f}°" for s in order], textposition="outside",
                textfont={"family": "JetBrains Mono", "size": 12, "color": col["text"]}))
            figr.update_layout(
                template="plotly_dark" if st.session_state.dark_mode else "plotly_white",
                height=max(280, n * 46 + 70),
                margin=dict(l=6, r=6, t=6, b=6),
                paper_bgcolor=col["surface"], plot_bgcolor=col["surface"],
                xaxis={"range": [-55, 55], "visible": False},
                yaxis={"autorange": "reversed",
                       "tickfont": {"family": "JetBrains Mono", "size": 12,
                                    "color": col["accent"]}})
            st.plotly_chart(figr, use_container_width=True)

        # ── Alert squilibrio ──────────────────────────────────
        als = []
        for a in syms:
            for b in syms:
                if a == b:
                    continue
                diff = P[a] - P[b]
                if abs(diff) >= 80:
                    verso = "LONG" if diff > 0 else "SHORT"
                    als.append(f"🔴 **{verso} {a}/{b}** — squilibrio estremo "
                               f"(Δperc {diff:.0f} · {a} {P[a]:.0f}° · {b} {P[b]:.0f}°). "
                               f"Conferma con setup volumetrico prima di operare.")
        if als:
            for a in als:
                st.error(a)
        else:
            st.success("Nessun differenziale oltre ±80°.")

        # ── Coppie affollate (blind spot della matrice) ─────────
        # La matrice sopra mostra P(riga)-P(colonna): se entrambe le
        # valute sono al proprio estremo NELLA STESSA direzione, il
        # differenziale è vicino a zero e la cella appare "neutra" —
        # ma è l'opposto: entrambe le gambe sono affollate, quindi il
        # posizionamento sulla coppia specifica non è un segnale
        # affidabile in nessuna delle due direzioni.
        pair_states = C.fx_pairs_ranked(FX)
        crowded = [p for p in pair_states if p["key"] == "crowded"]
        aligned = [p for p in pair_states if p["key"] in ("bull_aligned", "bear_aligned")]
        if crowded:
            st.markdown("**⚠️ Coppie affollate** — entrambe le gambe al proprio estremo "
                        "nella stessa direzione: la matrice le mostra come neutre, ma il "
                        "posizionamento qui non è utilizzabile come segnale direzionale.")
            for p in crowded:
                verso = "long" if p["pBase"] > 80 else "short"
                st.caption(f"🧊 **{p['pair']}** — {p['base']} {p['pBase']:.0f}° e "
                          f"{p['quote']} {p['pQuote']:.0f}° entrambe {verso} estremo: "
                          f"segnali che si annullano a vicenda.")
        # ── Primi segnali (accelerazione, indipendenti dal gate estremo) ──
        # A differenza di "avviso_inversione" sopra (che scatta solo se una
        # gamba è GIÀ al proprio estremo), questo guarda TUTTE le coppie
        # definite: cattura il caso di USD/CAD ancora lontano dagli
        # estremi ma con le due gambe che iniziano ad accelerare in
        # direzioni opposte — segnale anticipato, non un cambio di
        # ranking o classificazione.
        tutte = [{"pair": pr, **(C.fx_pair_state(pr, FX) or {})} for pr in C.FX_PAIRS]
        early = [p for p in tutte if p and p.get("traiettorie_divergenti")]
        if early:
            with st.expander(f"🔎 Primi segnali di divergenza traiettorie ({len(early)})",
                             expanded=True):
                st.caption("Le due gambe accelerano in direzioni opposte, anche se "
                          "ancora lontane dal proprio estremo storico (soglia rumore "
                          f"±{C.ACCEL_MIN:.0f}°). Precede l'avviso di inversione classico, "
                          "che scatta solo a estremo raggiunto.")
                for p in early:
                    st.caption(f"↔️ **{p['pair']}** — {p['direzione_traiettorie']} "
                              f"({p['base']} {p['pBase']:.0f}° · {p['quote']} {p['pQuote']:.0f}°)")

        if aligned:
            with st.expander(f"📋 Coppie con divergenza pulita ({len(aligned)})"):
                for p in aligned:
                    verso = "🟢 rialzista" if p["key"] == "bull_aligned" else "🔴 ribassista"
                    riga = (f"{verso} **{p['pair']}** — {p['base']} {p['pBase']:.0f}° "
                            f"vs {p['quote']} {p['pQuote']:.0f}° · divergenza {p['divergenza']:+.0f}")
                    st.caption(riga)
                    if p.get("avviso_inversione"):
                        st.caption(f"　　⚠️ {p['avviso_inversione']} — un solo tick, "
                                  f"non ancora un'inversione confermata, ma da monitorare.")

        # ── Dettaglio valuta (una o più, anche tutte) ───────────
        st.markdown("### Dettaglio valuta")
        # FIX StreamlitAPIException: prima il bottone scriveva su
        # st.session_state["fx_detail_multi"] DOPO che il multiselect con
        # quella stessa key era già stato istanziato nello stesso run —
        # Streamlit lo vieta esplicitamente. Ora: (1) inizializziamo lo
        # state una sola volta se manca, (2) il bottone lo aggiorna e fa
        # rerun PRIMA che il widget venga creato più sotto, (3) il
        # multiselect non passa più `default=` (ignorato comunque una
        # volta che la key esiste in session_state, quindi ridondante).
        if "fx_detail_multi" not in st.session_state:
            st.session_state["fx_detail_multi"] = [syms[0]] if syms else []

        c_sel1, c_sel2 = st.columns([4, 1])
        if c_sel2.button("Tutte", key="fx_detail_all"):
            st.session_state["fx_detail_multi"] = list(syms)
            st.rerun()

        fx_sel_list = c_sel1.multiselect(
            "Valute da sovrapporre", syms,
            key="fx_detail_multi",
            help="Seleziona una o più valute per confrontarne l'andamento del "
                 "net speculativo sullo stesso grafico.")
        # FIX KeyError nella sezione sotto (metriche/grafico/tabella
        # momentum): session_state["fx_detail_multi"] persiste tra i
        # rerun, ma se nel frattempo i dati COT vengono ricaricati con un
        # set di valute diverso (es. dopo il fix che ha aggiunto USD, o
        # se una valuta scende sotto la soglia minima di settimane), una
        # valuta rimasta selezionata da una sessione precedente non è più
        # una chiave di P/Z/D4 (costruiti solo su `syms` correnti) →
        # KeyError su P[s] appena sotto. Si scarta qui, silenziosamente,
        # qualunque simbolo non più valido.
        fx_sel_list = [s for s in fx_sel_list if s in P]

        if fx_sel_list:
            cols_d = st.columns(min(4, len(fx_sel_list)) or 1)
            for i, s in enumerate(fx_sel_list):
                cols_d[i % len(cols_d)].metric(
                    s, f"{P[s]:.0f}°", f"Z {Z[s]:.2f} · Δ4s {D4[s]:+.0f}")

            # Grafico storico netto speculativo (una o più valute).
            # Il prezzo in overlay ha senso solo con una singola valuta:
            # con più valute selezionate le scale di prezzo diverse (EUR/USD
            # vs USD/JPY vs indice USD) non sono confrontabili sullo stesso
            # asse, quindi si sovrapporrebbero in modo fuorviante.
            single = len(fx_sel_list) == 1
            fig_fx = make_subplots(specs=[[{"secondary_y": True}]]) if single else go.Figure()
            palette = [col["accent"], col["positive"], col["negative"],
                      col["warning"], col["text"], "#c084fc", "#38bdf8", "#f472b6"]
            for i, s in enumerate(fx_sel_list):
                v_s = C.series(FX[s], "nc")
                if len(v_s) < 10:
                    continue
                times_s = [pd.Timestamp(x["t"], unit="ms") for x in FX[s][-C.WINDOW:]]
                trace = go.Scatter(
                    x=times_s, y=v_s[-C.WINDOW:], name=s,
                    line=dict(color=palette[i % len(palette)], width=2),
                    fill="tozeroy" if single else None,
                    fillcolor=_rgba(palette[i % len(palette)], 0.08) if single else None,
                )
                if single:
                    fig_fx.add_trace(trace, secondary_y=False)
                else:
                    fig_fx.add_trace(trace)
            if single and fx_sel_list[0] in fx_prices:
                fx_sel = fx_sel_list[0]
                px = fx_prices[fx_sel]
                times_px = [pd.Timestamp(x["t"], unit="ms") for x in FX[fx_sel][-C.WINDOW:]]
                times_px = [t for t in times_px if t in px.index]
                px_vals = [float(px[t]) for t in times_px]
                fig_fx.add_trace(go.Scatter(x=times_px, y=px_vals,
                                 name="Prezzo",
                                 line=dict(color=col["warning"], width=1.8)),
                                 secondary_y=True)
            fig_fx.update_layout(
                template="plotly_dark" if st.session_state.dark_mode else "plotly_white",
                height=320 if not single else 280,
                margin=dict(l=10, r=10, t=10, b=10),
                paper_bgcolor=col["surface"], plot_bgcolor=col["surface"],
                legend={"orientation": "h", "y": 1.14,
                        "font": {"family": "JetBrains Mono", "size": 10.5}})
            st.plotly_chart(fig_fx, use_container_width=True)

            if single and fx_sel_list[0] in fx_divergence:
                fx_sel = fx_sel_list[0]
                dvg = fx_divergence[fx_sel]
                if dvg["divergent"]:
                    direzione = "prezzo sale ma posizionamento cala" if dvg["price_4w"] > 0 else "prezzo scende ma posizionamento sale"
                    st.warning(f"⚠️ **Divergenza {fx_sel}**: {direzione} (prezzo {dvg['price_4w']:+.1f}%, pos {dvg['pos_4w']:+.0f}°). "
                              f"Il movimento potrebbe esaurirsi.")
                else:
                    st.caption(f"Posizionamento e prezzo allineati (prezzo {dvg['price_4w']:+.1f}%, pos {dvg['pos_4w']:+.0f}°).")
            elif not single:
                st.caption("Overlay prezzo disattivato con più valute selezionate "
                          "(scale non comparabili). Seleziona una sola valuta per vederlo.")

            # Tabella momentum
            st.caption("**Momentum posizionamento**")
            mom_rows = []
            for s in syms:
                v_s = C.series(FX[s], "nc")
                if len(v_s) >= 10:
                    pct = C.percentile(v_s, v_s[-1])
                    d4 = C.deriv(v_s, w=4)
                    d8 = C.deriv(v_s, w=8)
                    trend = "🟢 rialzo" if d4 > 5 else ("🔴 calo" if d4 < -5 else "⚪ piatto")
                    mom_rows.append({
                        "Valuta": s, "Perc": f"{pct:.0f}°",
                        "Δ4s": f"{d4:+.0f}", "Δ8s": f"{d8:+.0f}",
                        "Trend": trend,
                    })
            if mom_rows:
                st.dataframe(pd.DataFrame(mom_rows), use_container_width=True, hide_index=True,
                             column_config={"Valuta": st.column_config.TextColumn("Valuta", width="small")})

# ══════════════════════════════════════════════════════════
with tab_cm:
    mk = [s for s in COMM_ORDER if len(COMM.get(s) or []) >= C.MINW]
    if not mk:
        st.info("Nessun dato materie prime valido: servono ≥ 52 settimane (usa 📥 Aggiornamento).")
    else:
        stati = {s: C.comm_state(s, COMM) for s in mk}

        if "cot_filter" not in st.session_state:
            st.session_state["cot_filter"] = "hot"
        bf1, bf2, bf3, bf4 = st.columns([1, 1, 1, 5])
        for c_, key, lab in ((bf1, "hot", "CALDI"), (bf2, "all", "TUTTI"),
                             (bf3, "bull", "▲"), (bf4, "bear", "▼")):
            if c_.button(lab, key=f"cotf_{key}",
                         type="primary" if st.session_state["cot_filter"] == key else "secondary"):
                st.session_state["cot_filter"] = key
                st.rerun()
        flt = st.session_state["cot_filter"]
        visible = [s for s in mk if (
            (flt == "all") or
            (flt == "hot" and stati[s]["tone"] != "muted") or
            (flt == "bull" and stati[s]["key"] == "bull") or
            (flt == "bear" and stati[s]["key"] == "bear"))]
        if not visible:
            visible = mk

        chips = "".join(
            f'<span style="display:inline-flex;align-items:center;gap:6px;'
            f'border:1px solid {col["border"]};border-radius:4px;padding:4px 8px;'
            f'margin:0 6px 6px 0;font-size:11px;color:{col["text"]};'
            f'background:{_rgba(TONE_COLOR[stati[s]["tone"]], 0.18)};">'
            f'<span style="width:8px;height:8px;border-radius:2px;'
            f'background:{TONE_COLOR[stati[s]["tone"]]};"></span>'
            f'{COMM_NAME.get(s, s)} · {stati[s]["pP"]:.0f}°</span>'
            for s in visible)
        hot_n = sum(1 for s in mk if stati[s]["tone"] != "muted")
        st.markdown(f'<div style="margin:6px 0 4px">{chips}</div>'
                    f'<div style="font-size:10.5px;color:{col["text_muted"]};'
                    f'margin-bottom:10px">{hot_n} / {len(mk)} con lettura attiva</div>',
                    unsafe_allow_html=True)

        opts = {s: COMM_NAME.get(s, s) for s in mk}
        if "cot_market" not in st.session_state or st.session_state["cot_market"] not in opts:
            st.session_state["cot_market"] = visible[0] if visible else mk[0]
        sym = st.selectbox("Mercato", list(opts.keys()),
                           format_func=lambda s: opts[s], label_visibility="collapsed")
        arr = COMM[sym]
        pA, mA, sA = C.series(arr, "prod"), C.series(arr, "mm"), C.series(arr, "swap")
        # x esplicito = date COT: senza, Plotly numera le settimane e le bande di
        # divergenza non si allineerebbero mai (e i buchi di dato sfalsano tutto).
        rr = arr[-C.WINDOW:]
        xset = [pd.Timestamp(int(x["t"]), unit="ms") for x in rr]
        pAx = [x.get("prod") for x in rr]
        mAx = [x.get("mm") for x in rr]
        sAx = [x.get("swap") for x in rr]
        px_all = [None] * len(rr)
        S = stati[sym]
        pP, pM, pS, dP, dM, revP = S["pP"], S["pM"], S["pS"], S["dP"], S["dM"], S["revP"]
        zP, zM = C.zscore(pA), C.zscore(mA)

        g1, g2 = st.columns([1.6, 1], gap="large")
        with g1:
            st.markdown(f"**Trasferimento rischio — {opts[sym]}** · {len(arr)} sett. "
                        f"· la linea ambra (asse destro) è il prezzo front-month.")
            show_price = st.checkbox("Sovrapponi prezzo dell'asset (asse destro)",
                                     value=True, key="cot_price_on")
            # il prezzo serve sempre (per le bande); show_price controlla solo se
            # disegnarne la linea
            close = prezzo_yf(C.YF_COMM.get(sym))
            if close is not None and len(close) > 1:
                px_all = [(None if pd.isna(v) else float(v))
                          for v in close.asof(pd.DatetimeIndex(xset))]
            # ── zone di divergenza operative ─────────────────────────
            zone = []
            if any(v is not None for v in px_all):
                zone = C.divergenze(arr, px_all)
            div_on = st.checkbox("Evidenzia le zone di divergenza sul grafico",
                                 value=True, key="cot_div_on")
            figc = make_subplots(specs=[[{"secondary_y": True}]])
            if div_on:
                for z in zone:
                    cazona = (col["positive"] if z["lato"] == "rialzista"
                              else col["negative"])
                    # NB: layout.Shape NON ha hovertemplate (plugin che esplode a
                    # runtime): il contenuto del tooltip va nell'annotazione.
                    figc.add_vrect(x0=xset[z["i"][0]], x1=xset[z["i"][1]],
                                   fillcolor=cazona, opacity=0.10, line_width=0,
                                   annotation_text=(f"{z['tipo']}"
                                                    f"<br>{z['settimane']}w"
                                                    + (f"<br>es {z['esito']:+.0f}%"
                                                       if z["esito"] is not None else "")),
                                   annotation_position="top left",
                                   annotation_font_size=8.5)
            figc.add_trace(go.Scatter(x=xset, y=pAx, name="Producer/Merchant",
                         line={"color": col["negative"], "width": 2},
                         fill="tozeroy", fillcolor=_rgba(col["negative"], 0.08)),
                         secondary_y=False)
            figc.add_trace(go.Scatter(x=xset, y=mAx, name="Managed Money",
                         line={"color": col["positive"], "width": 2}), secondary_y=False)
            figc.add_trace(go.Scatter(x=xset, y=sAx, name="Swap Dealer",
                         line={"color": col["accent"], "width": 1.5, "dash": "dash"}),
                         secondary_y=False)
            if show_price:
                if close is not None and len(close) > 1:
                    figc.add_trace(go.Scatter(x=xset, y=px_all,
                                 name="Prezzo (front-month)",
                                 line={"color": col["warning"], "width": 2.4},
                                 hovertemplate="prezzo %{y:.2f}<extra></extra>"),
                                 secondary_y=True)
                else:
                    st.caption(f"Prezzo non disponibile per {sym}: senza prezzo non "
                               "è possibile calcolare le divergenze (n/d, non 'zero "
                               "divergenze').")
            figc.update_layout(xaxis={"tickformat": "%b %y"},
                               hovermode="x unified")
            figc.update_layout(
                template="plotly_dark" if st.session_state.dark_mode else "plotly_white",
                height=340, margin=dict(l=10, r=10, t=10, b=10),
                paper_bgcolor=col["surface"], plot_bgcolor=col["surface"],
                legend={"orientation": "h", "y": 1.14,
                        "font": {"family": "JetBrains Mono", "size": 10.5}},
                font=dict(color=col["text"]))
            st.plotly_chart(figc, use_container_width=True)

            m1, m2, m3, m4, m5, m6, m7, m8 = st.columns(8)
            m1.metric("Prod perc", f"{pP:.0f}°")
            m2.metric("Managed perc", f"{pM:.0f}°")
            m3.metric("Swap perc", f"{pS:.0f}°")
            m4.metric("Prod inverte", "SÌ ✓" if revP else "no")
            m5.metric("Z Prod", f"{zP:.2f}")
            m6.metric("Z MM", f"{zM:.2f}")
            m7.metric("Δ Prod 2w", f"{dP:+.0f}")
            m8.metric("Δ MM 2w", f"{dM:+.0f}")

            # ── chi fa che cosa (semantica corretta, non "smart money") ──
            sw = C.swap_lettura(arr)
            pr = C.producer_lettura(arr)
            c1x, c2x = st.columns(2, gap="large")
            with c1x:
                st.markdown("**🟦 Swap Dealer — flusso, non opinione**")
                st.caption(f"{sw['pS']:.0f}° percentile · Δ 4 sett. {sw['dS']:+.0f} · "
                           f"**{sw['key']}** — {sw['txt']}")
                if sw["conferma"]:
                    st.caption("Confronto col Managed Money: " + sw["conferma"])
            with c2x:
                st.markdown("**🟥 Producer/Merchant — chi trasferisce rischio**")
                st.caption(f"{pr['pP']:.0f}° percentile · Δ 4 sett. {pr['dP']:+.0f} · "
                           + pr["txt"])
                st.caption("Incentivo leggibile ora: " + pr["incentivo"])

            # ── messaggio di stato: generato dalla CHIAVE dello stato, non da
            # condizioni duplicate qui (era l'origine dell'incoerenza con la
            # Bussola). La cornice dichiarata è in core/cot.py:_SEGNO_PROD.
            ESTREMO = (pr["estremo"] or "")
            if S["key"] == "bull":
                st.success(f"**CONTESTO RIALZISTA** · producer {pP:.0f}° (accumula o "
                           f"blocca costi) con spec non euforici ({pM:.0f}°)."
                           + ESTREMO + f" {pr['incentivo'].capitalize()}.")
            elif S["key"] == "bear":
                st.error(f"**CONTESTO RIBASSISTA** · producer {pP:.0f}° (vende "
                         f"copertura sui forti: non crede alla forza che vede) e "
                         f"Managed {pM:.0f}° long." + ESTREMO)
            if S["key"] in ("bull", "bear"):
                st.caption("Il percentile del lato reale ha "
                           + ("girato da <2 settimane: il movimento è fresco"
                              if revP else "già girato: il segnale non è più "
                              "freschissimo, è struttura"))
            elif S["key"] == "watch":
                st.warning(f"**SPECULATORI A ESTREMO** · Managed "
                           f"{'max long' if pM > 85 else 'max short'} ({pM:.0f}°) "
                           "senza invertimento del lato reale: trend maturo, non "
                           "inseguirlo e non contrattarlo ancora (servirebbe il "
                           "cambio della linea rossa/nera).")
            elif S["key"] == "trend":
                st.info(f"**TREND SPECULATIVO IN CORSO** · Managed "
                        f"{'accumula long' if dM > 0 else 'accumula short'} "
                        f"(Δ {dM:+.0f} vs producer {dP:+.0f}) in zona neutra: "
                        "non operare contro.")
            elif S["key"] == "hot_producer":
                st.warning(f"**PRODUCER ESTREMO** · {pP:.0f}°{ESTREMO}. Da solo non "
                           "dice né su né giù: dice che il premio per trasferire "
                           "rischio è a un estremo storico.")
            else:
                st.info(f"**NESSUNA LETTURA DOMINANTE** · producer {pP:.0f}° · "
                        f"Managed {pM:.0f}° · swap {pS:.0f}°. Contesto pulito: "
                        "nessuna posizione estrema da monitorare.")

        with g2:
            with st.expander("🧭 cornice di lettura (e come cambiarla)"):
                st.markdown(
                    """
Il **verso** con cui il percentile dei producer diventa "rialzista" o
"ribassista" è una scelta dichiarata, non la matematica: in `core/cot.py` c'è
`_SEGNO_PROD`.

* `+1` (attuale) — cornice *commerciale/accumulo*: percentile alto = il lato
  reale blocca costi o ricopre → positivo; percentile basso = vende copertura
  sui forti → negativo. Chip, messaggi e Bussola stanno tutti su questa.
* `-1` — cornice *hedge pressure / squeeze*: un producer molto short significa
  che poca copertura deve ancora essere venduta, quindi il percentile basso
  diventa positivo (era la lettura del codice prima della correzione — che però
  era incoerente con la sua stessa legenda).

Cambiando quel numero cambiano insieme le etichette di stato, il colore dei chip
**e** il contributo "Produttori" della Bussola: è l'unico posto da toccare, non
ci sono regole duplicate in giro. Nessuna delle due cornici è "vera": la CFTC
stessa avverte che classifica l'attività *prevalente* del trader, non ogni sua
posizione, e che parte dello storico è back-cast.
""")
            with st.expander(f"⚡ Divergenze prezzo/posizionamento ({len(zone)})",
                             expanded=bool(zone)):
                if not zone:
                    st.info("Nessuna zona: o il prezzo non è disponibile, o nelle "
                            "8 settimane mobili prezzo e posizionamento hanno "
                            "camminato nella stessa direzione (o con movimenti "
                            "sotto soglia). 'Nessuna zona' non è 'mercato pulito': "
                            "è 'nessuna evidenza in questa finestra'.")
                else:
                    tzz = pd.DataFrame([{
                        "tipo": z["tipo"],
                        "da": str(pd.Timestamp(int(z["t0"]), unit="ms").date()),
                        "a": str(pd.Timestamp(int(z["t1"]), unit="ms").date()),
                        "sett.": z["settimane"],
                        "linea": {"prod": "Producer", "mm": "Managed",
                                 "swap": "Swap"}[z["cat"]],
                        "lettura": ("prezzo su, copertura/giro OTC giù"
                                    if z["tipo"] == "COP-" or z["tipo"] == "CARB-"
                                    else "prezzo giù, posizionamento su"),
                        "lato": z["lato"],
                        "esito 13m": (f"{z['esito']:+.1f}%" if z["esito"] is not None
                                      else "n/d (fine storico)"),
                    } for z in zone[::-1]])
                    st.dataframe(tzz, use_container_width=True, hide_index=True,
                                 height=min(330, 40 + 34 * len(tzz)))
                    rs = C.Zones_summary(zone)
                    picco = rs["n"] < 8
                    st.caption(f"{rs['n']} zone in {len(arr)} settimane · "
                               + " · ".join(f"{k}: {v}" for k, v in rs["per_tipo"].items())
                               + ("" if rs["hit"] is None else
                                  (f" · esito a 13 settimane: {rs['hit']}% zone "
                                   "risoltesi dalla parte annunciata"
                                   + (" — campione troppo piccolo per parlarne come "
                                      "di 'tasso': è il conto delle settimane "
                                      "disponibili, non una statistica."
                                      if picco else ".")))
                               )
            with st.expander("📖 Come leggere le 3 linee + prezzo", expanded=True):
                st.markdown(
                    "**🟥 Producer/Merchant/Processor/User** (definizione CFTC: "
                    "*«entity that predominantly engages in the production, processing, "
                    "packing or handling of a physical commodity and uses the futures "
                    "markets to manage or hedge risks associated with those activities*»). "
                    "Qui dentro ci sono DUE incentivi opposti: chi deve **vendere** il "
                    "fisico teme il **ribasso** e si copre **short**; chi deve **comprarlo** "
                    "(refiner, mulino, food company) teme il **rialzo** e si copre **long**. "
                    "La linea è la *somma*: non dice «cosa prevede il produttore», dice chi "
                    "sta trasferendo rischio e a che condizioni. Il segnale utile è quindi "
                    "il **percentile** (rispetto alla storia di QUESTO mercato, non del "
                    "segno grezzo: quasi tutti sono strutturalmente short) e il **verso del "
                    "cambio**:\n"
                    "  · netto che **scende da livelli bassi** = vendono copertura sui "
                    "forti → il lato reale non crede al rally (cautela);\n"
                    "  · netto che **sale da livelli alti** = bloccano costi o ricoprono "
                    "-> il rischio fisico è già passato (costruttivo);\n"
                    "  · **ESTREMO** (pP<10): quasi tutto il fisico è già coperto → poca "
                    "vendita di copertura in arrivo, ed è la condizione dello *squeeze* se "
                    "il Managed Money è long.\n\n"
                    "**🟩 Managed Money** — speculazione vera (CTA, fondi, hedge fund): "
                    "sopra zero = long. Agli estremi il trend è maturo, non invertito.\n"
                    "**🟦 Swap Dealer** — non ha un'opinione: *«uses the futures markets to "
                    "manage or hedge the risk associated with those swaps transactions… "
                    "counterparties may be speculative traders, like hedge funds, or "
                    "traditional commercial clients»*. Il suo netto è la **conseguenza "
                    "meccanica dei flussi OTC dei clienti** (indici commodity: acquisto di "
                    "uno swap = il dealer compra futures; riscatto = vende). Perciò: il "
                    "**livello** dice poco (nel report Legacy stava dentro i «commercial», "
                    "ed è da lì che nasce il mito dello «smart money» commerciale); è "
                    "informativo il **cambio contro il prezzo**: prezzo che sale e swap che "
                    "riduce il netto = sta uscendo il compratore passivo, non un'idea; "
                    "prezzo che scende e swap che aumenta = domanda di esposizione che "
                    "arriva dall'OTC. Se si muove **nella stessa direzione** del Managed "
                    "Money, la mano è una sola (e se gira, gira doppia).\n"
                    "**🟨 Prezzo** (asse destro) — serve per le **divergenze**: bande verdi/"
                    "rosse sul grafico = settimane in cui prezzo e posizionamento hanno "
                    "detto cose opposte (COP± = lato fisico, CARB± = speculative/OTC). "
                    "Nelle note a piè di pagina i limiti dichiarati dalla stessa CFTC: la "
                    "classificazione è per *prevalent activity*, alcuni swap dealer fanno "
                    "attività commerciale e viceversa, e lo storico 2006-oggi è "
                    "*back-cast* con accuratezza decrescente.")
            with st.expander("⚙️ Configurazioni operative"):
                st.markdown(
                    "- **▲ RIALZISTA (CONTESTO)** — producer su minimi storici "
                    "(*quasi tutto il fisico è già venduto/coperto: poca offerta di "
                    "copertura in arrivo*) + Managed long = struttura tesa al rialzo. "
                    "Non è un segnale d'ingresso: il timing viene dall'inversione della "
                    "linea rossa o dalla conferma del prezzo.\n"
                    "- **▼ RIBASSISTA (CONTESTO)** — speculare: producer che torna a "
                    "coprirsi (netto che scende) mentre il Managed Money molla.\n"
                    "- **🔥 PRODUCER ESTREMO** — linea rossa al limite storico: da sola "
                    "non dice né su né giù; dice che il premio per trasferire rischio è "
                    "estremo. Aspetta l'inversione per il timing.\n"
                    "- **TREND VIVO** — Managed in trend *senza* estremi → non operare "
                    "contro.\n"
                    "- **⚡ COP− / COP+** — divergenza col **lato fisico**: prezzo su e "
                    "copertura che non cresce (o si riduce) = i detentori di fisico non "
                    "difendono quel livello; prezzo giù e netto che sale = blocco costi / "
                    "short covering.\n"
                    "- **⚡ CARB− / CARB+** — divergenza col **denaro**: prezzo su ma "
                    "Managed/Swap giù = salita senza carburante; prezzo giù maManaged/Swap "
                    "su = qualcuno assorbe. Le bande hanno l'esito a 13 settimane: usate "
                    "quel numero, non la vista.")
