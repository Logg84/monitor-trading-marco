import streamlit as st
import pandas as pd
import datetime
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from data_engine import DataEngine
from nav import render_navbar, section_header
from theme import get_theme

st.set_page_config(page_title="ARGO Regime", layout="wide", page_icon="🧭")

TH = get_theme()
PAL = {
    "dark": {
        "axis": "#94a3b8", "txt": "#e2e8f0", "annot_bg": "rgba(15,23,42,0.8)",
        "up": "#34d399", "down": "#f87171", "spx": "#60a5fa", "flip": "#fbbf24",
        "actor_g": "#a7f3d0", "actor_y": "#fde68a", "actor_r": "#fca5a5",
    },
    "light": {
        "axis": "#475569", "txt": "#0f172a", "annot_bg": "rgba(255,255,255,0.92)",
        "up": "#16a34a", "down": "#dc2626", "spx": "#2563eb", "flip": "#b45309",
        "actor_g": "#14532d", "actor_y": "#92400e", "actor_r": "#991b1b",
    },
}[TH["name"]]

st.markdown("""
<style>
.actor-box {
    background: var(--bg-panel); border: 1px solid var(--border);
    border-radius: 10px; padding: 12px 14px; margin-bottom: 10px;
}
.actor-box .emoji { font-size: 22px; }
.actor-box .label {
    font-family: 'IBM Plex Mono', monospace; font-size: 10px; font-weight: 700;
    text-transform: uppercase; letter-spacing: .08em; color: var(--txt-3); margin: 4px 0;
}
.actor-box .value { font-weight: 700; font-size: 13px; }
.actor-box .desc { font-size: 11.5px; color: var(--txt-2); margin-top: 4px; line-height: 1.5; }
.state-change-banner {
    background: var(--bg-panel); border: 1px solid var(--border);
    border-left: 5px solid #fbbf24; border-radius: 8px;
    padding: 10px 14px; margin: 8px 0; color: var(--txt-1);
}
</style>
""", unsafe_allow_html=True)

render_navbar("regime", hide_sidebar=True)
section_header("Bussola ARGO", "Analisi Regime & Attori di Mercato")

# ---------------------------------------------------------------
# MOTORE + BUSSOLA
# ---------------------------------------------------------------
if "engine" not in st.session_state:
    st.session_state["engine"] = DataEngine()
engine = st.session_state["engine"]

if "argo_prev_stato" not in st.session_state:
    st.session_state["argo_prev_stato"] = None
if "argo_prev_color" not in st.session_state:
    st.session_state["argo_prev_color"] = None
if "argo_state_changed" not in st.session_state:
    st.session_state["argo_state_changed"] = False

macro_info = engine.ottieni_bussola_argo()
macro_data = {"df": macro_info["df"], "latest": macro_info["latest"]}
latest = macro_info["latest"]
argo_bussola = macro_info["bussola"]

def check_state_change():
    prev_stato = st.session_state.get("argo_prev_stato")
    prev_color = st.session_state.get("argo_prev_color")
    current_stato = argo_bussola["stato"]
    current_color = argo_bussola["color"]
    if prev_stato is not None and prev_stato != current_stato:
        st.session_state["argo_state_changed"] = True
        st.session_state["argo_old_stato"] = prev_stato
        st.session_state["argo_old_color"] = prev_color
        st.session_state["argo_new_stato"] = current_stato
        st.session_state["argo_new_color"] = current_color
    else:
        st.session_state["argo_state_changed"] = False
    st.session_state["argo_prev_stato"] = current_stato
    st.session_state["argo_prev_color"] = current_color

check_state_change()

if st.session_state.get("argo_state_changed", False):
    old_stato = st.session_state.get("argo_old_stato", "N/D")
    new_stato = st.session_state.get("argo_new_stato", "N/D")
    old_color = st.session_state.get("argo_old_color", "slate")
    new_color = st.session_state.get("argo_new_color", "slate")
    color_map_hex = {
        "emerald": "#10b981", "rose": "#f43f5e", "amber": "#f59e0b",
        "indigo": "#6366f1", "orange": "#f97316", "slate": "#64748b"
    }
    st.markdown(f"""
    <div class="state-change-banner" style="border-left-color: {color_map_hex.get(new_color, '#fbbf24')};">
        <strong>⚠️ CAMBIO REGIME RILEVATO!</strong> <br>
        <span style="color: {color_map_hex.get(old_color, '#94a3b8')};"><b>{old_stato}</b></span>
        ➜
        <span style="color: {color_map_hex.get(new_color, '#fbbf24')};"><b>{new_stato}</b></span>
    </div>
    """, unsafe_allow_html=True)

color_map = {"emerald": "#10b981", "rose": "#f43f5e", "amber": "#f59e0b", "indigo": "#6366f1", "orange": "#f97316", "slate": "#64748b"}
st.markdown(f"""
<div style="background: var(--bg-panel); border: 1px solid var(--border); border-left: 5px solid {color_map[argo_bussola['color']]}; padding: 8px 14px; border-radius: 8px; margin-bottom: 18px; margin-top: 5px;">
    <div style="display: flex; justify-content: space-between; align-items: center; gap: 12px;">
        <div>
            <span style="font-size: 9px; font-weight: bold; text-transform: uppercase; color: var(--txt-3);">Direttiva Tattica</span>
            <h5 style="margin: 0; color: var(--txt-1); font-weight: 800; font-size: 1.15rem;">{argo_bussola['stato']}</h5>
            <p style="margin: 0; font-size: 12px; color: var(--txt-2); font-weight: 500;">{argo_bussola['desc']}</p>
        </div>
        <div style="background: var(--bg-base); border: 1px solid var(--border-strong); padding: 6px 12px; border-radius: 6px; text-align: center;">
            <span style="font-size: 8px; font-weight: bold; color: var(--txt-3); text-transform: uppercase;">BIAS</span>
            <h4 style="margin: 0; color: {color_map[argo_bussola['color']]}; font-weight: 900; font-size: 1.1rem;">{argo_bussola['bias']}</h4>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------
# ANALISI ATTORI
# ---------------------------------------------------------------
def analizza_attori(latest, df_plot):
    spot = latest["spot"]; vix = latest["vix"]; vvx = latest["vvx"]
    rapporto = latest["rapporto"]; flip = latest["flip"]
    upper = df_plot["Upper_Barrier"].iloc[-1] if "Upper_Barrier" in df_plot else spot * 1.05
    lower = df_plot["Lower_Barrier"].iloc[-1] if "Lower_Barrier" in df_plot else spot * 0.95
    mid = (upper + lower) / 2
    dist_from_mid = (spot - mid) / (upper - lower) if (upper - lower) != 0 else 0

    actors = {}
    if vvx < 90:
        actors["Istituzionale"] = {"emoji": "🏦", "status": "Coperture dormienti", "color": "🟢", "score": 1, "desc": "Flusso neutrale. Nessuna protezione massiccia in atto."}
    elif 90 <= vvx <= 105:
        actors["Istituzionale"] = {"emoji": "🏦", "status": "Allerta graduale", "color": "🟡", "score": 0, "desc": "Prudenza in aumento. Monitorare l'evoluzione."}
    else:
        actors["Istituzionale"] = {"emoji": "🏦", "status": "Panico / Coperture", "color": "🔴", "score": -1, "desc": "Coperture massive in atto. Rischio di crollo."}

    if dist_from_mid < -0.7:
        actors["Market Maker"] = {"emoji": "📊", "status": "Long Gamma", "color": "🟢", "score": 1, "desc": "Supporto solido sotto. Difendono i minimi."}
    elif dist_from_mid > 0.7:
        actors["Market Maker"] = {"emoji": "📊", "status": "Short Gamma", "color": "🔴", "score": -1, "desc": "Resistenza forte sopra. Frenano i rialzi."}
    else:
        actors["Market Maker"] = {"emoji": "📊", "status": "Neutrali", "color": "🟡", "score": 0, "desc": "Posizionamento bilanciato. Nessun estremo."}

    if vix > 25:
        actors["Retail"] = {"emoji": "🧑‍", "status": "Paura (Vendita)", "color": "🔴", "score": -1, "desc": "Panico retail. Minimi di mercato (contrarian buy)."}
    elif vix < 15:
        actors["Retail"] = {"emoji": "🧑‍", "status": "Euforia (Acquisto)", "color": "🟢", "score": 1, "desc": "Euforia retail. Massimi di mercato (contrarian sell)."}
    else:
        actors["Retail"] = {"emoji": "🧑‍💻", "status": "Neutrale", "color": "🟡", "score": 0, "desc": "Sentiment in attesa."}

    if vix < 18 and rapporto < 5:
        actors["Produttore"] = {"emoji": "🏭", "status": "Buyback Window", "color": "🟢", "score": 1, "desc": "Capitale a basso costo. Emissioni/buyback favorevoli."}
    elif vix > 22 or rapporto > 7:
        actors["Produttore"] = {"emoji": "🏭", "status": "Window Chiusa", "color": "🔴", "score": -1, "desc": "Costo del capitale alto. Stop alle emissioni."}
    else:
        actors["Produttore"] = {"emoji": "🏭", "status": "Neutrale", "color": "🟡", "score": 0, "desc": "Condizioni miste."}

    if spot >= flip:
        actors["Trend Macro"] = {"emoji": "🌍", "status": "Trend Following", "color": "🟢", "score": 1, "desc": "Mercato premia i trend. Momento positivo."}
    else:
        actors["Trend Macro"] = {"emoji": "🌍", "status": "Mean Reversion", "color": "🔴", "score": -1, "desc": "Mercato premia i rimbalzi. Attenzione ai supporti."}

    if vix < 18:
        actors["Gestore Rischio"] = {"emoji": "🎯", "status": "Rischio Controllato", "color": "🟢", "score": 1, "desc": "De-risking in attesa. Flusso stabile."}
    elif 18 <= vix <= 22:
        actors["Gestore Rischio"] = {"emoji": "🎯", "status": "Soglia Allerta", "color": "🟡", "score": 0, "desc": "Monitoraggio. Possibile riduzione esposizione."}
    else:
        actors["Gestore Rischio"] = {"emoji": "🎯", "status": "De-risking Attivo", "color": "🔴", "score": -1, "desc": "Pressione al ribasso sistemica. Vendita forzata."}

    scores = [v["score"] for v in actors.values()]
    avg_score = sum(scores) / len(scores)
    composite_score = int(((avg_score + 1) / 2) * 100)

    retail_score = actors["Retail"]["score"]; inst_score = actors["Istituzionale"]["score"]
    mm_score = actors["Market Maker"]["score"]; macro_score = actors["Trend Macro"]["score"]
    risk_score = actors["Gestore Rischio"]["score"]

    sintesi = ""
    if retail_score == 1 and inst_score == -1:
        sintesi = "⚠️ **ALLARME TOP**: Il retail è euforico (VIX < 15) ma le istituzioni si stanno coprendo massicciamente (VVIX > 105). Scenario tipico di un top di breve/medio termine. **Valutare riduzione dell'esposizione o hedging.**"
    elif retail_score == -1 and mm_score == 1:
        sintesi = "✅ **OPPORTUNITÀ BOTTOM**: Il retail sta vendendo per paura (VIX > 25) ma i Market Maker sono long gamma e difendono il supporto. Tipico setup da rimbalzo. **Iniziare ad accumulare gradualmente.**"
    elif macro_score == 1 and risk_score == -1:
        sintesi = "⚡ **CONFLITTO TREND/RISCHIO**: Il trend macro è positivo, ma il gestore del rischio sta riducendo l'esposizione (VIX > 22). Il mercato potrebbe subire scossoni improvvisi. **Mantenere le posizioni ma allargare gli stop loss.**"
    elif avg_score >= 0.5 and macro_score == 1 and inst_score >= 0 and mm_score >= 0:
        sintesi = "📈 **TREND CONFORTEVOLE**: Istituzionali, Market Maker e Trend Macro sono allineati sul rialzo. Il quadro è costruttivo. **Mantenere le posizioni e valutare eventuali aggiunte sui ritracciamenti.**"
    elif avg_score <= -0.5 and macro_score == -1:
        sintesi = "⛔ **RISCHIO SISTEMICO**: Trend macro negativo, gestori del rischio in de-risking e istituzioni coperte. **Evitare nuovi ingressi. Proteggere il capitale.**"
    elif -0.3 < avg_score < 0.3:
        sintesi = "🔍 **MERCATO LATERALE/CONTRASTATO**: I segnali sono misti. **Attendere una convergenza tra i diversi attori prima di prendere posizioni direzionali.**"
    else:
        if avg_score > 0:
            sintesi = f"📊 **LEGGERO BIAS POSITIVO** (Score: {composite_score}/100). Il quadro generale è costruttivo ma non unanime. **Privilegiare ingressi selettivi sui titoli di qualità.**"
        else:
            sintesi = f"📊 **LEGGERO BIAS NEGATIVO** (Score: {composite_score}/100). Il quadro generale è cauto. **Privilegiare la prudenza e attendere segnali più forti.**"

    return actors, composite_score, sintesi

# ---------------------------------------------------------------
# CORPO VISTA REGIME
# ---------------------------------------------------------------
df_plot = macro_data["df"].copy()
df_plot['Rolling_Std'] = df_plot['SPX'].rolling(window=20, min_periods=1).std()
df_plot['Upper_Barrier'] = df_plot['Flip_Line'] + (2 * df_plot['Rolling_Std'])
df_plot['Lower_Barrier'] = df_plot['Flip_Line'] - (2 * df_plot['Rolling_Std'])

st.subheader("🔍 Sala di Controllo Multi-Attore")
actors, composite_score, sintesi = analizza_attori(latest, df_plot)

col_sint1, col_sint2 = st.columns([3, 1])
with col_sint1:
    if composite_score >= 60:
        bg_color, border_color = "rgba(34, 197, 94, 0.15)", "#22c55e"
    elif composite_score >= 40:
        bg_color, border_color = "rgba(234, 179, 8, 0.15)", "#eab308"
    else:
        bg_color, border_color = "rgba(239, 68, 68, 0.15)", "#ef4444"
    st.markdown(f"""
    <div style="background-color: {bg_color}; border: 1px solid var(--border); border-left: 5px solid {border_color}; padding: 12px 15px; border-radius: 8px; margin-bottom: 10px;">
        <div style="font-size: 14px; font-weight: 500; color: var(--txt-1);">{sintesi}</div>
        <div style="font-size: 11px; color: var(--txt-3); margin-top: 5px;">
            🕒 Aggiornato: {datetime.datetime.now().strftime('%H:%M:%S')} | Composite Score: {composite_score}/100
        </div>
    </div>
    """, unsafe_allow_html=True)

with col_sint2:
    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number", value=composite_score, domain={'x': [0, 1], 'y': [0, 1]},
        gauge={'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': PAL["txt"]}, 'bar': {'color': "#fbbf24"},
               'steps': [{'range': [0, 40], 'color': "rgba(239, 68, 68, 0.4)"}, {'range': [40, 60], 'color': "rgba(234, 179, 8, 0.4)"}, {'range': [60, 100], 'color': "rgba(34, 197, 94, 0.4)"}],
               'threshold': {'line': {'color': PAL["txt"], 'width': 4}, 'thickness': 0.75, 'value': composite_score}},
        title={'text': "<b>Rischio / Rendimento</b>", 'font': {'size': 14, 'color': PAL["txt"]}}
    ))
    fig_gauge.update_layout(template=TH["chart"]["template"], height=150, margin=dict(l=10, r=10, t=30, b=10),
                            paper_bgcolor=TH["chart"]["paper"], plot_bgcolor=TH["chart"]["plot"],
                            font=dict(color=TH["chart"]["text"]))
    st.plotly_chart(fig_gauge, use_container_width=True)

st.markdown("### 📌 Prospettive dei Singoli Attori")
actor_keys = ["Istituzionale", "Market Maker", "Retail", "Produttore", "Trend Macro", "Gestore Rischio"]
cols = st.columns(3)
for i, key in enumerate(actor_keys):
    actor = actors[key]
    col = cols[i % 3]
    color_text = {"🟢": PAL["actor_g"], "🟡": PAL["actor_y"], "🔴": PAL["actor_r"]}.get(actor["color"], PAL["txt"])
    with col:
        st.markdown(f"""
        <div class="actor-box" style="border-left: 3px solid {color_text};">
            <div class="emoji">{actor['emoji']}</div>
            <div class="label">{key}</div>
            <div class="value" style="color: {color_text};">{actor['color']} {actor['status']}</div>
            <div class="desc">{actor['desc']}</div>
        </div>
        """, unsafe_allow_html=True)

st.markdown("---")
st.subheader("📊 Dettaglio Tecnico (Dati Grezzi)")

col_chart1, col_chart2 = st.columns([2, 1])
with col_chart1:
    fig1 = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.08, subplot_titles=(None, "Protezioni Attive nel Mercato (VVIX)"))
    fig1.add_trace(go.Scatter(x=df_plot["Date"], y=df_plot["SPX"], mode='lines', name='S&P 500', line=dict(color=PAL["spx"], width=2.5)), row=1, col=1)
    fig1.add_trace(go.Scatter(x=df_plot["Date"], y=df_plot["Flip_Line"], mode='lines', name='Flip Line (MA 20)', line=dict(color=PAL["flip"], width=2, dash='dash')), row=1, col=1)
    fig1.add_trace(go.Scatter(x=df_plot["Date"], y=df_plot["Upper_Barrier"], mode='lines', name='Barriera Sup (+2σ)', line=dict(color=PAL["down"], width=1.5, dash='dot')), row=1, col=1)
    fig1.add_trace(go.Scatter(x=df_plot["Date"], y=df_plot["Lower_Barrier"], mode='lines', name='Barriera Inf (-2σ)', line=dict(color=PAL["up"], width=1.5, dash='dot')), row=1, col=1)
    fig1.add_trace(go.Scatter(x=pd.concat([df_plot["Date"], df_plot["Date"][::-1]]), y=pd.concat([df_plot["Upper_Barrier"], df_plot["Lower_Barrier"][::-1]]), fill='toself', fillcolor='rgba(148, 163, 184, 0.15)', line=dict(color='rgba(255,255,255,0)'), showlegend=False, hoverinfo='skip'), row=1, col=1)
    gamma_color = 'rgba(34, 197, 94, 0.15)' if argo_bussola['bias'] == 'LONG' else 'rgba(239, 68, 68, 0.15)'
    fig1.add_trace(go.Scatter(x=pd.concat([df_plot["Date"], df_plot["Date"][::-1]]), y=pd.concat([df_plot["SPX"], df_plot["Flip_Line"][::-1]]), fill='toself', fillcolor=gamma_color, line=dict(color='rgba(255,255,255,0)'), showlegend=False, hoverinfo='skip'), row=1, col=1)
    last_date = df_plot["Date"].iloc[-1]; last_spx = df_plot["SPX"].iloc[-1]; last_flip = df_plot["Flip_Line"].iloc[-1]
    fig1.add_annotation(x=last_date, y=last_spx, text=f"S&P {last_spx:.2f}", showarrow=True, arrowhead=1, arrowcolor=PAL["spx"], row=1, col=1, bgcolor=PAL["annot_bg"], font=dict(color=PAL["spx"], size=11))
    fig1.add_annotation(x=last_date, y=last_flip, text=f"Flip {last_flip:.2f}", showarrow=True, arrowhead=1, arrowcolor=PAL["flip"], row=1, col=1, bgcolor=PAL["annot_bg"], font=dict(color=PAL["flip"], size=11))
    fig1.add_trace(go.Bar(x=df_plot["Date"], y=df_plot["VVIX"], name='VVIX (Coperture)', marker_color='rgba(244, 114, 182, 0.7)', marker_line_color='rgba(244, 114, 182, 1)', marker_line_width=0.5), row=2, col=1)
    fig1.add_hline(y=105, line_dash="dash", line_color="#ef4444", opacity=0.9, row=2, col=1, annotation_text="⚡ ALLERTA (105)", annotation_position="top right")
    fig1.add_hline(y=90, line_dash="dash", line_color=PAL["axis"], opacity=0.5, row=2, col=1, annotation_text="Soglia Controllo", annotation_position="bottom right")
    fig1.update_layout(template=TH["chart"]["template"], height=500, margin=dict(l=0, r=0, t=20, b=0), hovermode='x unified',
                       legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10)),
                       paper_bgcolor=TH["chart"]["paper"], plot_bgcolor=TH["chart"]["plot"], font=dict(color=TH["chart"]["text"]))
    fig1.update_yaxes(title_text="Prezzo S&P 500", row=1, col=1, color=PAL["axis"], gridcolor=TH["chart"]["grid"])
    fig1.update_yaxes(title_text="VVIX", row=2, col=1, color=PAL["axis"], gridcolor=TH["chart"]["grid"])
    fig1.update_xaxes(title_text="Data", row=2, col=1, color=PAL["axis"], gridcolor=TH["chart"]["grid"])
    st.plotly_chart(fig1, use_container_width=True)
    st.caption("📖 Legenda: Linea blu = S&P 500 · gialla tratteggiata = Flip Line (SMA20) · punteggiate = barriere ±2σ · area verde/rossa = gamma (sopra la Flip = trend positivo) · istogramma rosa = VVIX (sopra 105 = coperture istituzionali in allarme).")

with col_chart2:
    ratio_val = argo_bussola['rapporto']
    if ratio_val < 5.0:
        gauge_color, status_text = PAL["axis"], "⚡ MOLLA PRONTA"
    elif 5.0 <= ratio_val <= 7.0:
        gauge_color, status_text = "#22c55e", "📈 TREND IDEALE"
    else:
        gauge_color, status_text = "#ef4444", "🌪️ SCOSSONI ESTREMI"
    fig2 = go.Figure(go.Indicator(
        mode="gauge+number+delta", value=ratio_val, domain={'x': [0, 1], 'y': [0, 1]},
        delta={'reference': 6.0, 'valueformat': '.2f', 'font': {'color': PAL["txt"]}},
        gauge={'axis': {'range': [0, 10], 'tickwidth': 1, 'tickcolor': PAL["txt"]}, 'bar': {'color': gauge_color},
               'steps': [{'range': [0, 4.9], 'color': "rgba(148, 163, 184, 0.2)"}, {'range': [5.0, 7.0], 'color': "rgba(34, 197, 94, 0.3)"}, {'range': [7.1, 10], 'color': "rgba(239, 68, 68, 0.2)"}],
               'threshold': {'line': {'color': PAL["txt"], 'width': 4}, 'thickness': 0.75, 'value': ratio_val}},
        title={'text': f"<b>{status_text}</b><br><span style='font-size:12px; color:{PAL['axis']};'>VVIX / VIX</span>", 'font': {'color': PAL["txt"]}}
    ))
    fig2.update_layout(template=TH["chart"]["template"], height=350, margin=dict(l=20, r=20, t=50, b=20),
                       paper_bgcolor=TH["chart"]["paper"], plot_bgcolor=TH["chart"]["plot"], font=dict(color=TH["chart"]["text"]))
    st.plotly_chart(fig2, use_container_width=True)
    st.caption("📖 Termometro: < 5.0 = molla (accumulo) · 5.0–7.0 = trend ideale · > 7.0 = scossoni (rischio).")

st.subheader("🧠 Volatilità Istituzionale: VIX vs VVIX")
fig3 = make_subplots(specs=[[{"secondary_y": True}]])
fig3.add_trace(go.Scatter(x=df_plot["Date"], y=df_plot["VIX"], name="VIX (Volatilità Implicita)", line=dict(color=PAL["spx"], width=2)), secondary_y=False)
fig3.add_trace(go.Scatter(x=df_plot["Date"], y=df_plot["VVIX"], name="VVIX (Volatilità del VIX)", line=dict(color="#f472b6", width=2, dash='dot')), secondary_y=True)
fig3.add_hline(y=105, line_dash="dash", line_color="#ef4444", opacity=0.5, secondary_y=True, annotation_text="ALLERTA 105")
fig3.add_hline(y=90, line_dash="dash", line_color=PAL["axis"], opacity=0.3, secondary_y=True)
fig3.update_layout(template=TH["chart"]["template"], height=300, margin=dict(l=0, r=0, t=40, b=0), hovermode='x unified',
                   paper_bgcolor=TH["chart"]["paper"], plot_bgcolor=TH["chart"]["plot"], font=dict(color=TH["chart"]["text"]))
fig3.update_yaxes(title_text="VIX", secondary_y=False, color=PAL["axis"], gridcolor=TH["chart"]["grid"])
fig3.update_yaxes(title_text="VVIX", secondary_y=True, color=PAL["axis"])
st.plotly_chart(fig3, use_container_width=True)
st.caption("💡 VVIX > 105 con VIX < 25 = falso segnale di calma: le istituzioni si stanno già coprendo (anticipo di crollo).")
