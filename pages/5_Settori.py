"""
Settori — trend e divergenza capitalizzazione (CW) vs pesi uguali (EW), su
una tassonomia standard e non inventata.

LIVELLO 1 · 11 settori GICS: per ognuno Select Sector SPDR (cap-w) e Invesco
S&P 500 Equal Weight dello stesso settore — sono gli STESSI titoli pesati in
modo diverso, quindi il Δ è effetto di pesatura puro.
LIVELLO 2 · sotto-settori S&P Select Industry (i SPDR "SPDR S&P <Industria>",
equal-weighted by design) dove il gemello a capitalizzazione esiste; dove non
esiste il Δ è n/d, mai zero.
LIVELLO 3 · temi che GICS non contiene (oro, uranio, solare, IA, agribusiness):
tabella separata, per non spacciarli per categorie di classificazione.

Doppia rappresentazione: tabelle NUMERICHE (momentum delle due gambe, Δ su
1/3/6 mesi, consistenza e durata del vantaggio, posizione del rapporto EW/CW
nel proprio range annuo) e rappresentazione GRAFICA (heatmap Δ, heatmap gambe,
barre Δ ordinate, andamento del rapporto EW/CW, dettaglio per settore con le
gambe e i singoli ETF).

Il settore è CONTESTO, mai segnale: non aggiunge né toglie punti 🟡/🟢 e non
partecipa al pruning. Priorità = Bottom Score + bonus settore (±10): ordina,
non decide. Lettura, mai ordine — non è consulenza.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Settori", page_icon="🏭", layout="wide",
                   initial_sidebar_state="collapsed")

from ui.theme import inject_css, COLORS, style_fig
from ui.nav import render_navbar, sidebar_nav
from core.data_engine import load_screening_cache
from core.sectors import (BENCHMARK, SECTORS, SUBSECTORS, THEMES, freschezza,
                          indexed, legs_detail, sector_label, sector_rows,
                          sector_series, sub_rows, theme_rows, trend_table,
                          snapshot_and_source, vento)

if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = True

inject_css(dark=st.session_state.dark_mode)
render_navbar(title="Settori")
sidebar_nav()

c_refresh, _ = st.columns([1, 6])
if c_refresh.button("🔄 Aggiorna settori", type="secondary"):
    st.cache_data.clear()
    st.rerun()

col = COLORS["dark"] if st.session_state.dark_mode else COLORS["light"]


def _heat(vals: list[list], y: list[str], x: list[str], cbar: str):
    """Heatmap con NUMERI nelle celle (plotly non è affidabile con %{z:+.1f},
    quindi il testo è pre-formattato e i numeri reali restano sullo hover)."""
    z, txt = [], []
    for row in vals:
        z.append([0.0 if v is None or pd.isna(v) else round(float(v), 1) for v in row])
        txt.append(["—" if v is None or pd.isna(v) else f"{float(v):+.1f}" for v in row])
    base = "#111318" if st.session_state.dark_mode else "#FFFFFF"
    return go.Figure(go.Heatmap(
        z=z, x=x, y=y, text=txt, texttemplate="%{text}", textfont=dict(size=10),
        colorscale=[[0, col["negative"]], [0.5, base], [1, col["positive"]]],
        colorbar=dict(title=cbar, thickness=10, len=0.9)))


def _num(df: pd.DataFrame, cols: list[str], dec: int = 1) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
            if dec == 0:
                out[c] = out[c].round(0).astype("Int64")
            else:
                out[c] = out[c].round(dec)
    return out


CFG_NUM = {c: st.column_config.NumberColumn(c, format="%+.1f", width="small")
           for c in ("CW 1m", "CW 3m", "CW 6m", "EW 1m", "EW 3m", "EW 6m",
                     "Δ 1m", "Δ 3m", "Δ 6m", "RS 3m", "Range Δ")}

st.markdown("## Settori — trend & divergenza CW / EW")
st.caption(
    "Δ = momentum della gamba a pesi uguali meno quello della gamba a "
    "capitalizzazione, sullo stesso perimetro di titoli. Δ>0 = moto diffuso "
    "(molte teste partecipano): il titolo medio ha più probabilità di rendere. "
    "Δ<0 = trascinano i pesi massimi. Stato 0-100 = 25% trend (SMA50/SMA200) + "
    "25% momentum 3m + 15% momentum 6m + 15% forza relativa 3m vs "
    f"{BENCHMARK} + 10% posizione su 52 sett. + 10% Δ (breadth)."
)

snap, ssrc = snapshot_and_source()
if not (snap or {}).get("rows"):
    st.error("Nessun dato di settore (né live né cache del repo): senza dati il "
             "pannello non dice nulla. 'n/d' non è 'neutro'.")
    st.stop()
_b = (snap or {}).get("bench_mom63")
st.caption(
    f"Dati = chiusure giornaliere di 1 anno · {freschezza(snap, ssrc == 'live')} · "
    f"{len(SECTORS)} settori GICS, {len(SUBSECTORS)} sotto-settori, {len(THEMES)}"
    f" temi · mercato {BENCHMARK}"
    + (f" 3m {float(_b):+.1f}%." if _b is not None else ".")
    + " Frequenza: job `settori-eod` alle 21:35 UTC nei giorni di borsa aperta "
    "(dopo la chiusura di Wall Street), in più i due run di screening e un "
    "download live all'apertura pagina (cache 1 ora). `🔄 Aggiorna settori` "
    "forza un reload immediato.")

srows, _ = sector_rows()
subrows, _ = sub_rows()
trows, _ = theme_rows()
tG = _num(trend_table(srows), [], 0)
tS = _num(trend_table(subrows), [], 0)
tT = _num(trend_table(trows), [], 0)

tab_g, tab_s, tab_t, tab_c = st.tabs(
    ["🌍 Settori GICS", "🔬 Sotto-settori (Select Industry)",
     "🎨 Temi (fuori tassonomia)", "🎯 Candidati per settore"])

# ══════════════════════════════════════════════ LIVELLO 1 · GICS 11
with tab_g:
    st.markdown("#### I 11 settori GICS — la spina del portale")
    st.caption("`Select Sector SPDR` (capitalizzazione) e `Invesco S&P 500 Equal "
               "Weight <settore>` (pesi uguali) pesano gli STESSI titoli dello "
               "stesso indice: il Δ è puro effetto di pesatura. Ordini per "
               "settore GICS, non per sensazione.")
    f1, f2, f3 = st.columns([2, 2, 1])
    win = f1.radio("Finestra del Δ", ["1m", "3m", "6m"], horizontal=True, index=1,
                   key="g_win")
    ordg = f2.radio("Ordina per", ["Δ", "Score", "Momentum 3m", "Settore"],
                    horizontal=True, index=0, key="g_ord")
    solopair = f3.toggle("solo Δ disponibile", value=False, key="g_pair",
                         help="Filtra i settori con entrambe le gambe (tutti e "
                              "11, qui: il filtro serve se aggiungi settori "
                              "senza gemello)")
    dcol = {"1m": "Δ 1m", "3m": "Δ 3m", "6m": "Δ 6m"}[win]
    vg = tG.copy()
    if solopair:
        vg = vg[vg[dcol].notna()]
    key_ord = {"Δ": dcol, "Score": "Score", "Momentum 3m": "CW 3m",
               "Settore": "Settore"}[ordg]
    vg = vg.sort_values(key_ord, ascending=(ordg == "Settore"),
                        na_position="last").reset_index(drop=True)

    st.dataframe(vg[["Settore", "Etichetta CW", "Etichetta EW", "Stato", "Score",
                    "CW 1m", "CW 3m", "CW 6m", "EW 1m", "EW 3m", "EW 6m",
                    "Δ 1m", "Δ 3m", "Δ 6m", "RS 3m", "Consistenza", "Streak",
                    "Range Δ", "Pos 52", "Guida"]],
                 use_container_width=True, hide_index=True,
                 height=min(520, 42 + 35 * len(vg)),
                 column_config={
                     "Score": st.column_config.ProgressColumn(
                         "Score", min_value=0, max_value=100, format="%d"),
                     "Etichetta CW": st.column_config.TextColumn("CW (cap-w)"),
                     "Etichetta EW": st.column_config.TextColumn("EW (pesi ùguali)"),
                     "Consistenza": st.column_config.NumberColumn(
                         "Consist. %", format="%d", width="small",
                         help="Sedute su 63 in cui il rapporto EW/CW stava sopra "
                              "la propria SMA20: continuità del vantaggio."),
                     "Streak": st.column_config.NumberColumn(
                         "Fila", format="%+d", width="small",
                         help="Sedute consecutive di vantaggio: + EW, − CW."),
                     "RS 3m": st.column_config.NumberColumn("RS 3m", format="%+.1f",
                                                            width="small"),
                     **CFG_NUM})

    m1, m2, m3, m4 = st.columns(4)
    gn = tG.dropna(subset=["Δ 3m"])
    m1.metric("Settori con EW sopra CW (3m)", f"{int((tG['Δ 3m'] > 0).sum())}",
              f"{int((tG['Δ 3m'] < 0).sum())} sotto")
    m2.metric("Δ 3m medio", "n/d" if gn.empty else f"{gn['Δ 3m'].mean():+.1f} pt")
    if not gn.empty:
        m3.metric("Vantaggio EW massimo", gn.sort_values("Δ 3m").iloc[-1]["Settore"],
                  f"{gn['Δ 3m'].max():+.1f} pt")
        m4.metric("Vantaggio CW massimo", gn.sort_values("Δ 3m").iloc[0]["Settore"],
                  f"{gn['Δ 3m'].min():+.1f} pt")

    if len(gn) >= 2:
        c1, c2 = st.columns([3, 2])
        with c1:
            fig = _heat([gn[c].tolist() for c in ("Δ 1m", "Δ 3m", "Δ 6m")],
                        gn["Settore"].tolist(), ["1 mese", "3 mesi", "6 mesi"], "Δ pt")
            style_fig(fig, st.session_state.dark_mode,
                      height=max(320, 30 * len(gn) + 80))
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            fig2 = _heat([tG.sort_values("CW 3m", ascending=False)[c].tolist()
                          for c in ("CW 3m", "EW 3m", "Δ 3m", "RS 3m")],
                         tG.sort_values("CW 3m", ascending=False)["Settore"].tolist(),
                         ["CW 3m %", "EW 3m %", "Δ 3m pt", "RS pt"], "")
            style_fig(fig2, st.session_state.dark_mode,
                      height=max(320, 30 * len(tG) + 80))
            st.plotly_chart(fig2, use_container_width=True)

        bar = gn[["Settore", "Δ 3m"]].sort_values("Δ 3m")
        fig3 = go.Figure(go.Bar(
            y=bar["Settore"], x=bar["Δ 3m"], orientation="h",
            marker_color=[col["positive"] if v > 0 else col["negative"]
                          for v in bar["Δ 3m"]],
            text=[f"{v:+.1f} pt" for v in bar["Δ 3m"]], textposition="outside",
            textfont=dict(size=9),
            hovertemplate="%{y}<br>Δ %{x:+.1f} pt<extra></extra>"))
        fig3.update_layout(xaxis_title=f"Δ EW−CW ({win}, pt)",
                           xaxis_range=[min(bar["Δ 3m"].min(), 0) * 1.7,
                                        max(bar["Δ 3m"].max(), 0) * 1.7])
        style_fig(fig3, st.session_state.dark_mode, height=max(300, 26 * len(bar) + 60))
        st.plotly_chart(fig3, use_container_width=True)

    st.markdown("#### Rapporto EW/CW: dove si è formata la divergenza")
    def_lbl = tG.dropna(subset=["Δ 3m"]).sort_values("Δ 3m", ascending=False)[
        "key"].head(5).tolist() + tG.dropna(subset=["Δ 3m"]).sort_values("Δ 3m")[
        "key"].head(3).tolist()
    sel_g = st.multiselect("Settori da sovrapporre (rapporto EW/CW, indice 100)",
                           tG["key"].tolist(), default=def_lbl,
                           format_func=lambda k: sector_label(k), key="g_sel")
    serG = sector_series(tuple(sel_g), window=252) if sel_g else pd.DataFrame()
    if serG.empty:
        st.info("Nessuna serie disponibile per la selezione.")
    else:
        spd = serG[[c for c in serG.columns if c.startswith("Δ ·")]]
        if spd.empty:
            st.info("Nessun rapporto: i settori scelti non hanno gemello EW.")
        else:
            ix = indexed(spd) * 100.0
            fgr = go.Figure()
            for c in ix.columns:
                fgr.add_trace(go.Scatter(x=ix.index, y=ix[c], name=c.split(" · ", 1)[-1],
                                         line=dict(width=1.6), mode="lines"))
            fgr.add_hline(y=100, line_dash="dot", line_color=col["text_muted"],
                          annotation_text="parità", annotation_position="top left")
            fgr.update_layout(yaxis_title="EW/CW (indice 100; sopra 100 = guida EW)",
                              legend=dict(orientation="h", y=-0.35))
            style_fig(fgr, st.session_state.dark_mode, height=390, showlegend=True)
            st.plotly_chart(fgr, use_container_width=True)
            st.caption("Scese ripide = il settore diventa un gioco di mega-cap; "
                       "rimonte = tornano dentro le seconde linee. Per il titolo "
                       "medio conta questa pendenza più del livello del Δ.")

    with st.expander("🧾 Gamba per gamba (i singoli ETF dei 11 settori)"):
        ld = legs_detail(tuple(tG["key"]))
        if ld.empty:
            st.info("Nessuna gamba disponibile.")
        else:
            st.dataframe(_num(ld.rename(columns={
                "gamba": "Gamba", "etf": "ETF", "mom21": "1m %", "mom63": "3m %",
                "mom126": "6m %", "rs63": "RS 3m", "pos52": "Pos 52s.",
                "label": "Settore", "livello": "Livello", "gics": "GICS"}),
                ["1m %", "3m %", "6m %", "RS 3m", "Pos 52s."]),
                use_container_width=True, hide_index=True,
                height=min(640, 42 + 33 * len(ld)))

# ══════════════════════════════════════ LIVELLO 2 · SELECT INDUSTRY
with tab_s:
    st.markdown("#### Sotto-settori S&P Select Industry")
    st.caption("Sono i SPDR «S&P <Industria>», indice modified equal-weight by "
               "design: qui il confronto CW↔EW ha senso SOLO dove il gemello a "
               "capitalizzazione esiste (chip, software, farmaci, biotech, E&P, "
               "aerospazio, case, retail). Dove manca, la riga dice 'solo EW': il "
               "trend si legge, il Δ no — e non viene messo a zero. Colonna "
               "'GICS' = settore di appartenenza secondo la classificazione, non "
               "una famiglia inventata da chi scrive.")
    f0, f1, f2 = st.columns([1.4, 2.6, 2])
    solo_cestini = f0.toggle("solo con paniere quotato", value=True, key="s_cest",
                             help="Molti sotto-settori S&P Select Industry non "
                                  "hanno un ETF dedicato: restano 'n/d'. Nascosti "
                                  "per default, per non leggere il vuoto.")
    filtri_g = f1.multiselect("Mostra solo sotto-settori di questi settori GICS",
                              [k for k in SECTORS], default=[], key="s_filtro_g",
                              format_func=lambda k: sector_label(k))
    s_ord = f2.radio("Ordina per", ["Δ", "Score", "Settore"], horizontal=True,
                     index=0, key="s_ord")
    vs = tS.copy()
    if solo_cestini:
        vs = vs[(vs["Etichetta CW"] != "—") | (vs["Etichetta EW"] != "—")]
    if filtri_g:
        vs = vs[vs["GICS"].isin([sector_label(k) for k in filtri_g])]
    vs = vs.sort_values({"Δ": "Δ 3m", "Score": "Score", "Settore": "Settore"}[s_ord],
                        ascending=(s_ord == "Settore"), na_position="last")
    st.dataframe(vs[["Settore", "GICS", "Stato", "Score", "CW 1m", "CW 3m", "CW 6m",
                     "EW 1m", "EW 3m", "EW 6m", "Δ 1m", "Δ 3m", "Δ 6m", "RS 3m",
                     "Consistenza", "Streak", "Range Δ", "Pos 52", "Guida",
                     "Lettura"]],
                 use_container_width=True, hide_index=True,
                 height=min(660, 42 + 33 * len(vs)),
                 column_config={
                     "Lettura": st.column_config.TextColumn(
                         "Lettura", help="'gamba EW (CW assente)' = il trend è "
                                         "dell'equal-weighted, Δ non calcolabile."),
                     **CFG_NUM})

    _solo = tS[(tS["Etichetta CW"] != "—") | (tS["Etichetta EW"] != "—")]
    st.caption(f"{len(_solo)} sotto-settori su {len(tS)} hanno un paniere quotato "
               "almeno su una gamba; gli altri sono solo etichette di "
               "classificazione (nessun ETF = nessun numero, non 'neutro').")
    sn = tS.dropna(subset=["Δ 3m"]).sort_values("Δ 3m", ascending=False)
    st.markdown("##### Δ per sotto-settore (dove le due gambe esistono)")
    if len(sn) >= 2:
        fig4 = _heat([sn[c].tolist() for c in ("Δ 1m", "Δ 3m", "Δ 6m")],
                     sn["Settore"].tolist(), ["1 mese", "3 mesi", "6 mesi"], "Δ pt")
        style_fig(fig4, st.session_state.dark_mode, height=max(300, 29 * len(sn) + 80))
        st.plotly_chart(fig4, use_container_width=True)
        bar4 = sn[["Settore", "Δ 3m", "GICS"]].sort_values("Δ 3m")
        fig5 = go.Figure(go.Bar(
            y=bar4["Settore"], x=bar4["Δ 3m"], orientation="h",
            marker_color=[col["positive"] if v > 0 else col["negative"]
                          for v in bar4["Δ 3m"]],
            text=[f"{v:+.1f}" for v in bar4["Δ 3m"]], textposition="outside",
            textfont=dict(size=9), customdata=bar4["GICS"],
            hovertemplate="%{y} (%{customdata})<br>Δ %{x:+.1f} pt<extra></extra>"))
        fig5.update_layout(xaxis_title="Δ EW−CW 3 mesi (pt)")
        style_fig(fig5, st.session_state.dark_mode, height=max(300, 27 * len(bar4) + 60))
        st.plotly_chart(fig5, use_container_width=True)
    else:
        st.info("Pochi sotto-settori con gemello EW: Δ non confrontabile.")

    st.markdown("##### Dettaglio sotto-settore")
    kdet = st.selectbox("Sotto-settore", tS["key"].tolist(), key="s_det",
                        format_func=lambda k: f"{tS.set_index('key').loc[k, 'Settore']}"
                                              f" · {sector_label(SUBSECTORS[k].get('gics'))}")
    rw = tS[tS["key"] == kdet].iloc[0]
    ser = sector_series((kdet,), window=126)
    if ser.empty:
        st.warning("Serie non disponibile (n/d): non è un settore debole.")
    else:
        cw_c = [c for c in ser.columns if c.startswith("CW ·")]
        ew_c = [c for c in ser.columns if c.startswith("EW ·")]
        ix = indexed(ser[cw_c + ew_c])
        fig6 = go.Figure()
        for i, c in enumerate(ix.columns):
            fig6.add_trace(go.Scatter(
                x=ix.index, y=ix[c], name=c.split(" · ")[1] if " · " in c else c,
                line=dict(width=2, dash="solid" if c in cw_c else "dot",
                          color=col["accent"] if c in cw_c else col["positive"])))
        fig6.update_layout(yaxis_title="indice 100 all'inizio della finestra",
                           legend=dict(orientation="h", y=-0.3))
        style_fig(fig6, st.session_state.dark_mode, height=360, showlegend=True)
        st.plotly_chart(fig6, use_container_width=True)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Stato", rw["Stato"], "n/d" if pd.isna(rw["Score"]) else f"{rw['Score']}/100",
              delta_color="off")
    c2.metric("Momentum 3m", "n/d" if pd.isna(rw["CW 3m"]) else f"{rw['CW 3m']:+.1f}%",
              ("EW " + ("n/d" if pd.isna(rw["EW 3m"]) else f"{rw['EW 3m']:+.1f}%")))
    c3.metric("Δ EW−CW 3m", "n/d" if pd.isna(rw["Δ 3m"]) else f"{rw['Δ 3m']:+.1f} pt")
    c4.metric("Consistenza · fila",
              "n/d" if pd.isna(rw["Consistenza"]) else f"{rw['Consistenza']:.0f}%",
              "n/d" if pd.isna(rw["Streak"]) else f"{rw['Streak']:+.0f} sedute",
              delta_color="off")
    c5.metric("Rapporto EW/CW", "n/d" if pd.isna(rw["Range Δ"]) else f"{rw['Range Δ']:.0f}% range",
              rw["Guida"], delta_color="off")
    if str(rw.get("Note") or "").strip():
        st.caption(rw["Note"])
    _v = vento(kdet, subrows)
    st.caption("Vento di questo sotto-settore: "
               + {"favore": "a favore (guida l'equal-weighted)",
                  "contro": "contro (guida la capitalizzazione)",
                  "misto": "misto/laterale"}.get(_v, "non calcolabile (n/d)")
               + " — i 11 settori GICS stanno nel primo tab, le definizioni "
                 "nell'ultimo expander.")
    ld2 = legs_detail((kdet,))
    if not ld2.empty:
        st.dataframe(_num(ld2.rename(columns={"gamba": "Gamba", "etf": "ETF",
                                              "mom21": "1m %", "mom63": "3m %",
                                              "mom126": "6m %", "rs63": "RS 3m",
                                              "pos52": "Pos 52s."}),
                          ["1m %", "3m %", "6m %", "RS 3m", "Pos 52s."]),
                     use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════ LIVELLO 3 · TEMI
with tab_t:
    st.markdown("#### Temi che non sono categorie di classificazione")
    st.caption("Oro & preziosi, uranio, solare, energia pulita, robotica/IA, "
               "agribusiness, rame, retail: **non sono settori né industry group "
               "GICS**, sono panieri tematici a capitalizzazione, spesso senza "
               "alcun gemello equal-weighted. Stanno qui separati proprio per non "
               "fingere che la loro assenza di Δ sia 'breadth neutra'. Nessun Δ "
               "significa: nessun confronto possibile, non 'nessun vantaggio'.")
    tt_t = tT.sort_values("Score", ascending=False, na_position="last")
    st.dataframe(tt_t[["Settore", "Etichetta CW", "Etichetta EW", "Stato", "Score",
                       "CW 1m", "CW 3m", "CW 6m", "EW 3m", "Δ 3m", "RS 3m",
                       "Pos 52", "Lettura"]],
                 use_container_width=True, hide_index=True,
                 height=min(430, 42 + 35 * len(tt_t)),
                 column_config={**CFG_NUM,
                                "Lettura": st.column_config.TextColumn(
                                    "Lettura", help="Indica se il trend è letto su "
                                                    "una gamba sola."),
                                "Δ 3m": st.column_config.NumberColumn(
                                    "Δ 3m", format="%+.1f",
                                    help="Vuoto = nessun prodotto equal-weighted "
                                         "sullo stesso perimetro.")})
    n_ew = int(tT["Δ 3m"].notna().sum())
    st.caption(f"{n_ew} temi su {len(tT)} hanno un confronto EW↔CW; gli altri "
               "sono leggibili solo in momentum/forza relativa.")

# ══════════════════════════════════════════════════ CANDIDATI
with tab_c:
    st.caption("Unione della cache screening (data/screening_latest.csv, scritta "
               "dal CI) con i due livelli: è la tabella che risponde a 'dove metto "
               "l'attenzione oggi'. Priorità = Bottom + bonus settore (±10).")
    dfc, meta = load_screening_cache()
    if dfc is None or dfc.empty:
        st.info("Nessuna cache di screening: avvia lo Screening o aspetta il job CI.")
    elif "Sector" not in dfc.columns:
        st.info("Cache screening senza colonne di settore: riesegui lo screening.")
    else:
        sig = dfc[dfc["Segnale"].astype(str).str.startswith(("🟡", "🟢"))].copy()
        if sig.empty:
            st.info("Nessun candidato 🟡/🟢 nell'ultima scansione.")
        else:
            cols = [c for c in ("Ticker", "Nome", "Settore", "Sotto-settore",
                                "Sector", "Vento", "Δ EW−CW", "SottoΔ", "Segnale",
                                "Bottom", "Priorità", "DD%", "Wyckoff")
                    if c in sig.columns]
            st.dataframe(sig[cols].sort_values("Priorità", ascending=False,
                                               na_position="last"),
                         use_container_width=True, hide_index=True,
                         height=min(500, 42 + 34 * len(sig)),
                         column_config={
                             "Δ EW−CW": st.column_config.NumberColumn(
                                 "Δ settore", format="%+.1f"),
                             "SottoΔ": st.column_config.NumberColumn(
                                 "Δ sotto", format="%+.1f"),
                             "Priorità": st.column_config.NumberColumn(
                                 "Priorità", format="%d",
                                 help="Bottom + bonus settore: ordina, non decide.")})
            vv = (sig["Vento"].value_counts() if "Vento" in sig.columns
                  else pd.Series(dtype=int))
            m1, m2, m3 = st.columns(3)
            m1.metric("Segnali con vento a favore", int(vv.get("favore", 0)))
            m2.metric("Segnali con vento contro", int(vv.get("contro", 0)))
            m3.metric("Senza lettura / laterali",
                      int(vv.get("nd", 0)) + int(vv.get("misto", 0)))
            if int(vv.get("contro", 0)):
                st.warning("I candidati su settore in calo restano VALIDI: è il "
                           "contesto a suggerire size più piccola, attesa di "
                           "conferma o priorità più bassa. Nessuna regola cambia.")

with st.expander("📖 Come si legge, la tassonomia usata e i limiti"):
    st.markdown(
        "**Tassonomia.** Livello 1 = i 11 settori GICS (S&P Dow Jones Indices / "
        "MSCI), con le coppie Select Sector SPDR ↔ Invesco S&P 500 Equal Weight "
        "(stesso indice, pesi diversi). Livello 2 = S&P Select Industry (i SPDR "
        "mono-industria, equal-weighted by design), agganciati al settore GICS di "
        "appartenenza. Livello 3 = temi fuori classificazione, isolati.\n\n"
        "**Perché non ho creato famiglie.** Un raggruppamento 'Primari' con "
        "agricoltura e oro, o 'Tecnologia' con chip e media, mescola driver diversi "
        "(meteo/commodity vs tassi reali; ciclo semiconduttori vs abbonamenti) e "
        "rende il Δ una media di cose non confrontabili. Con GICS + Select Industry "
        "ogni Δ ha un significato singolo.\n\n"
        "**Δ (EW−CW)** — il titolo medio rende quando guidano i pesi uguali; "
        "**consistenza/fila** — distingue un regime da un rimbalzo; **RS vs "
        "mercato** — toglie il beta: +20% con RS ~0 è il mercato che sale; "
        "**posizione del rapporto EW/CW sul proprio range** — dice se la guida è "
        "una novità o una struttura.\n\n"
        "**Limiti.** I proxy sono ETF USA: su titoli europei il driver locale (FX, "
        "ciclo, regolamentazione) non c'è. I XL* sono ~S&P 500 (mega-cap) mentre "
        "gli(equal-weighted Select Industry sono all-cap: i livelli 1 e 2 non sono "
        "sovrapponibili titolo per titolo. La famiglia equal-weight ribilancia per "
        "quota e paga più fee (0,40% vs 0,08-0,10%): una parte del Δ è strutturale, "
        "non informativa. GICS ha le sue note dolenti (Alphabet e Meta in "
        "Communication Services, Tesla in Consumer Discretionary): la classificazione "
        "è una convenzione, non una verità economica. Soglie e pesi sono dichiarati "
        "su ~1 anno di storico: è un termometro, non una previsione."
    )
