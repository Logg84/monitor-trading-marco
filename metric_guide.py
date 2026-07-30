"""
Guida visiva alle metriche operative (Quality Score · Bottom Score · Size Suggerita).
Modulo isolato: render_metric_guide() disegna un pannello apribile con schede
vive e un calcolatore interattivo della Size. Chiamato da pages/2_Screening.py.

NOTA RENDERING: _GUIDE_CSS DEVE essere avvolto in <style>...</style>, altrimenti
Streamlit (unsafe_allow_html) lo stampa come testo grezzo invece di interpretarlo.
"""
import streamlit as st

_GUIDE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap');

.mg-wrap { position: relative; }
.mg-wrap::before {
    content: ""; position: absolute; inset: -8px -8px auto -8px; height: 160px;
    background: radial-gradient(700px 140px at 12% 0%, rgba(56,189,248,.08), transparent 70%),
                radial-gradient(520px 120px at 88% 0%, rgba(245,158,11,.07), transparent 70%);
    pointer-events: none; border-radius: 14px;
}

.mg-card {
    position: relative; background: linear-gradient(160deg, #0f172a 0%, #0c1322 100%);
    border: 1px solid #1e293b; border-left: 4px solid var(--mg-accent, #38bdf8);
    border-radius: 14px; padding: 18px 20px 20px 20px; height: 100%;
    box-shadow: 0 18px 40px -28px rgba(0,0,0,.9);
    transition: transform .18s ease, border-color .2s ease, box-shadow .2s ease;
}
.mg-card:hover {
    transform: translateY(-3px); border-color: var(--mg-accent, #38bdf8);
    box-shadow: 0 26px 50px -26px color-mix(in srgb, var(--mg-accent, #38bdf8) 55%, transparent);
}
.mg-kicker {
    font-family: 'IBM Plex Mono', monospace; font-size: 10px; font-weight: 600;
    letter-spacing: .2em; text-transform: uppercase; color: var(--mg-accent, #38bdf8);
    margin: 0 0 4px 0;
}
.mg-title {
    font-family: 'Space Grotesk', sans-serif; font-weight: 700; font-size: 1.35rem;
    letter-spacing: -0.02em; color: #f8fafc; margin: 0 0 2px 0; line-height: 1.05;
}
.mg-sub {
    font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: #7c8aa3;
    margin: 0 0 14px 0; letter-spacing: .02em;
}

/* scala 0->4 */
.mg-scale { display: flex; gap: 6px; margin: 0 0 16px 0; }
.mg-seg {
    flex: 1; text-align: center; border-radius: 8px; padding: 8px 2px 6px 2px;
    background: #0b1220; border: 1px solid #243049;
    transition: transform .15s ease, box-shadow .2s ease, border-color .2s ease;
}
.mg-seg:hover { transform: translateY(-3px) scale(1.04); border-color: var(--mg-c); box-shadow: 0 8px 18px -10px var(--mg-c); }
.mg-seg .n { font-family: 'Space Grotesk', sans-serif; font-weight: 700; font-size: 1.25rem; color: var(--mg-c); line-height: 1; }
.mg-seg .t { font-family: 'IBM Plex Mono', monospace; font-size: 8.5px; color: #64748b; margin-top: 4px; letter-spacing: .04em; }

.mg-h {
    font-family: 'Space Grotesk', sans-serif; font-weight: 600; font-size: .82rem;
    color: #cbd5e1; margin: 14px 0 7px 0; letter-spacing: .01em;
}
.mg-what { font-size: 13px; color: #94a3b8; line-height: 1.55; margin: 0 0 4px 0; }
.mg-what b { color: #e2e8f0; }
.mg-hl { color: var(--mg-accent, #38bdf8); font-weight: 600; }

.mg-crit { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.mg-crit li {
    display: flex; align-items: flex-start; gap: 9px; font-size: 12.5px; color: #cbd5e1; line-height: 1.4;
    background: rgba(255,255,255,.015); border: 1px solid #1b2435; border-radius: 8px; padding: 7px 10px;
    transition: border-color .2s ease, background .2s ease, transform .15s ease;
}
.mg-crit li:hover { border-color: var(--mg-accent, #38bdf8); background: rgba(56,189,248,.05); transform: translateX(2px); }
.mg-crit .ck { color: var(--mg-accent, #38bdf8); font-weight: 700; flex: 0 0 auto; }
.mg-crit .no { color: #475569; font-weight: 700; flex: 0 0 auto; }
.mg-crit code { font-family: 'IBM Plex Mono', monospace; color: #e2e8f0; background: #0b1220; padding: 0 4px; border-radius: 4px; font-size: 11px; }

/* legenda semaforica */
.mg-leg { display: flex; flex-direction: column; gap: 5px; margin-top: 4px; }
.mg-leg .row { display: flex; align-items: center; gap: 9px; font-size: 12px; color: #cbd5e1; }
.mg-leg .dot { width: 9px; height: 9px; border-radius: 50%; flex: 0 0 auto; box-shadow: 0 0 10px -2px currentColor; }
.mg-leg .row b { color: #f1f5f9; font-family: 'IBM Plex Mono', monospace; }

/* calcolatore size */
.mg-calc {
    margin-top: 6px; background: #0a101d; border: 1px solid #1c2740; border-radius: 12px; padding: 16px;
}
.mg-formula {
    font-family: 'IBM Plex Mono', monospace; font-size: 13px; color: #94a3b8; text-align: center;
    margin: 0 0 14px 0; letter-spacing: .02em;
}
.mg-formula b { color: #e2e8f0; }
.mg-result {
    text-align: center; background: linear-gradient(135deg, rgba(56,189,248,.10), rgba(14,165,233,.04));
    border: 1px solid rgba(56,189,248,.3); border-radius: 12px; padding: 14px 10px; margin-top: 14px;
}
.mg-result .big {
    font-family: 'Space Grotesk', sans-serif; font-weight: 700; font-size: 2.6rem; line-height: 1;
    color: #38bdf8; letter-spacing: -0.03em;
}
.mg-result .big.zero { color: #ef4444; }
.mg-result .unit { font-family: 'IBM Plex Mono', monospace; font-size: 1rem; color: #64748b; }
.mg-result .break { font-family: 'IBM Plex Mono', monospace; font-size: 11.5px; color: #94a3b8; margin-top: 8px; }
.mg-result .break .v { color: #e2e8f0; }
.mg-result .mode { margin-top: 9px; font-size: 12.5px; font-weight: 600; }

.mg-factors { display: flex; flex-direction: column; gap: 8px; margin-top: 4px; }
.mg-factor {
    display: grid; grid-template-columns: 130px 1fr; gap: 10px; align-items: center;
    background: rgba(255,255,255,.015); border: 1px solid #1b2435; border-radius: 8px; padding: 8px 12px;
}
.mg-factor .fname { font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: #38bdf8; letter-spacing: .03em; }
.mg-factor .fdesc { font-size: 12px; color: #cbd5e1; }
.mg-factor .fdesc code { font-family: 'IBM Plex Mono', monospace; color: #e2e8f0; background: #0b1220; padding: 0 4px; border-radius: 4px; }

.mg-note {
    margin-top: 14px; font-size: 12px; color: #94a3b8; line-height: 1.5;
    border-top: 1px solid #1b2435; padding-top: 12px;
}
.mg-note b { color: #fca5a5; }
</style>
"""

# colori della scala 0->4
_SCALE_COLORS = ["#ef4444", "#f97316", "#eab308", "#84cc16", "#22c55e"]
_SCALE_TAGS_Q = ["sotto", "debole", "medio", "solido", "top"]
_SCALE_TAGS_B = ["nessuno", "1 segn.", "2 segn.", "3 segn.", "pieno"]


def _scale_html(tags):
    segs = []
    for i, c in enumerate(_SCALE_COLORS):
        segs.append(
            f'<div class="mg-seg" style="--mg-c:{c}"><div class="n">{i}</div>'
            f'<div class="t">{tags[i]}</div></div>'
        )
    return '<div class="mg-scale">' + "".join(segs) + "</div>"


def _card_quality():
    return f"""
    <div class="mg-card" style="--mg-accent:#22c55e">
      <p class="mg-kicker">Qualità fondamentale</p>
      <h3 class="mg-title">Quality Score</h3>
      <p class="mg-sub">solidità vs il suo indice · scala 0 → 4</p>
      {_scale_html(_SCALE_TAGS_Q)}
      <p class="mg-what">Misura quanto il titolo è <b>finanziariamente solido</b> rispetto agli
      altri titoli <span class="mg-hl">dello stesso indice</span> che sono in sconto in quel momento.
      Non è un voto assoluto: è un <b>confronto con la mediana del gruppo</b>.</p>
      <p class="mg-h">I 4 criteri (+1 ciascuno se migliore della mediana)</p>
      <ul class="mg-crit">
        <li><span class="ck">✓</span><span><code>Debt / Equity</code> ≤ mediana → meno debito dei pari</span></li>
        <li><span class="ck">✓</span><span><code>Free Cash Flow</code> ≥ mediana → genera più cassa dei pari</span></li>
        <li><span class="ck">✓</span><span><code>Operating Margin</code> ≥ mediana → margine operativo superiore</span></li>
        <li><span class="ck">✓</span><span><code>Return on Equity</code> ≥ mediana → redditività del capitale superiore</span></li>
      </ul>
      <p class="mg-h">Come leggerlo</p>
      <div class="mg-leg">
        <div class="row"><span class="dot" style="color:#22c55e"></span><b>3–4</b>&nbsp; azienda strutturalmente forte: candidata seria all'accumulo</div>
        <div class="row"><span class="dot" style="color:#eab308"></span><b>2</b>&nbsp; nella media del gruppo: serve conferma tecnica</div>
        <div class="row"><span class="dot" style="color:#ef4444"></span><b>0–1</b>&nbsp; fondamenta deboli: anche se è in sconto, cautela</div>
      </div>
    </div>
    """


def _card_bottom():
    return f"""
    <div class="mg-card" style="--mg-accent:#f59e0b">
      <p class="mg-kicker">Segnali tecnici di inversione</p>
      <h3 class="mg-title">Bottom Score</h3>
      <p class="mg-sub">la caduta sta finendo? · scala 0 → 4</p>
      {_scale_html(_SCALE_TAGS_B)}
      <p class="mg-what">Misura se la <b>discesa sta rallentando</b> e compaiono i primi segnali
      di rimbalzo. Risponde a: <span class="mg-hl">è il momento di entrare, o sto ancora
      afferrando un coltello che cade?</span></p>
      <p class="mg-h">I 4 pilastri (+1 ciascuno quando scatta)</p>
      <ul class="mg-crit">
        <li><span class="ck">✓</span><span><b>Decelerazione ROC</b> — la velocità di discesa a 70gg sta migliorando rispetto a 15gg fa</span></li>
        <li><span class="ck">✓</span><span><b>MACD histogram</b> — l'ultima barra è più alta della precedente (momento che gira)</span></li>
        <li><span class="ck">✓</span><span><b>Vicino a un POC</b> strutturale con momentum positivo (prezzo su zona di volume forte)</span></li>
        <li><span class="ck">✓</span><span><b>Volume + Force Index</b> in aumento (c'è forza dietro il movimento)</span></li>
      </ul>
      <p class="mg-what" style="margin-top:8px">La <span class="mg-hl">convergenza VWAP</span>
      (2+ VWAP vicini) rafforza il pilastro POC: in convergenza piena il punteggio può toccare
      un picco oltre 4, letto comunque come <b>massimo</b>.</p>
      <p class="mg-h">Come leggerlo</p>
      <div class="mg-leg">
        <div class="row"><span class="dot" style="color:#22c55e"></span><b>4</b>&nbsp; 🟢 inversione confermata: pronto per l'ingresso</div>
        <div class="row"><span class="dot" style="color:#eab308"></span><b>3</b>&nbsp; 🟡 segnali iniziali: monitora, manca una conferma</div>
        <div class="row"><span class="dot" style="color:#f59e0b"></span><b>2</b>&nbsp; 🟡 esaurimento vendita: la caduta rallenta, pazienza</div>
        <div class="row"><span class="dot" style="color:#ef4444"></span><b>0–1</b>&nbsp; 🔴 nessuna inversione: non entrare, può scendere ancora</div>
      </div>
    </div>
    """


def _factors_html():
    return """
    <div class="mg-factors">
      <div class="mg-factor"><span class="fname">① BASE</span><span class="fdesc">per <b>dimensione</b>:
        <code>≥10B</code> → 10% · <code>2–10B</code> → 5% · <code>&lt;2B</code> → 2%</span></div>
      <div class="mg-factor"><span class="fname">② QUALITÀ</span><span class="fdesc">per <b>Quality Score</b>:
        <code>3–4</code> → ×1.2 · <code>2</code> → ×1.0 · <code>0–1</code> → ×0.6</span></div>
      <div class="mg-factor"><span class="fname">③ REGIME</span><span class="fdesc">per <b>Bussola ARGO</b>:
        <code>LONG</code> → ×1.0 · <code>NEUTRO</code> → ×0.6 · <code>SHORT</code> → ×0.3</span></div>
    </div>
    """


def _calc_widget():
    c1, c2, c3 = st.columns(3)
    with c1:
        fascia = st.selectbox("Fascia di capitalizzazione",
            ["Large cap (≥ 10 B€)", "Mid cap (2–10 B€)", "Small cap (< 2 B€)"],
            key="mg_cap", label_visibility="collapsed")
    with c2:
        qual = st.selectbox("Quality Score",
            ["3–4 (sopra la mediana)", "2 (nella media)", "0–1 (sotto la mediana)"],
            key="mg_qual", label_visibility="collapsed")
    with c3:
        reg = st.selectbox("Regime ARGO",
            ["🟢 LONG (tendenza)", "🟡 NEUTRO (laterale)", "🔴 SHORT (discesa)"],
            key="mg_reg", label_visibility="collapsed")

    base = {"Large cap (≥ 10 B€)": 10.0, "Mid cap (2–10 B€)": 5.0, "Small cap (< 2 B€)": 2.0}[fascia]
    qm = {"3–4 (sopra la mediana)": 1.2, "2 (nella media)": 1.0, "0–1 (sotto la mediana)": 0.6}[qual]
    rm = {"🟢 LONG (tendenza)": 1.0, "🟡 NEUTRO (laterale)": 0.6, "🔴 SHORT (discesa)": 0.3}[reg]
    raw = base * qm * rm
    final = round(raw, 1)
    if final < 1.0:
        final = 0.0

    is_short = reg.startswith("🔴")
    if is_short and final == 0.0:
        mode_txt, mode_col = "⛔ NON ENTRARE (regime SHORT, size azzerata)", "#ef4444"
    elif is_short:
        mode_txt, mode_col = "⏳ LIMITE — size ridotta (regime SHORT)", "#f59e0b"
    else:
        mode_txt, mode_col = "✅ Posizione aperta ai livelli indicati", "#22c55e"

    zero_cls = " zero" if final == 0.0 else ""
    st.markdown(
        '<div class="mg-result">'
        f'<div class="big{zero_cls}">{final:.1f}<span class="unit"> %</span></div>'
        '<div class="break">'
        f'<span class="v">{base:.0f}</span> base &nbsp;×&nbsp; <span class="v">{qm:.1f}</span> qualità '
        f'&nbsp;×&nbsp; <span class="v">{rm:.1f}</span> regime &nbsp;=&nbsp; <span class="v">{raw:.2f}</span>'
        + (' &nbsp;→&nbsp; sotto 1% = <span class="v" style="color:#ef4444">0</span>' if raw < 1.0 else '')
        + '</div>'
        f'<div class="mode" style="color:{mode_col}">{mode_txt}</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def _card_size():
    return f"""
    <div class="mg-card" style="--mg-accent:#38bdf8">
      <p class="mg-kicker">Dimensione della posizione</p>
      <h3 class="mg-title">Size Suggerita</h3>
      <p class="mg-sub">quanto pesare il titolo nel portafoglio · % del capitale</p>
      <p class="mg-what">Non è un prezzo, è una <b>quota di capitale</b>. Nasce da tre fattori
      moltiplicati tra loro: più l'azienda è grande, solida e il mercato è favorevole,
      più la posizione è pesante. In regime di discesa la size viene <span class="mg-hl">tagliata
      fino ad azzerarsi</span>.</p>
      <p class="mg-formula"><b>size</b> = base × qualità × regime &nbsp;·&nbsp; se &lt; 1% → <b style="color:#ef4444">0</b></p>
      {_factors_html()}
    </div>
    """


def render_metric_guide():
    st.markdown(_GUIDE_CSS, unsafe_allow_html=True)
    with st.expander("📖  Guida alle metriche — Quality · Bottom · Size  (apri per spiegare una colonna)", expanded=False):
        st.markdown('<div class="mg-wrap"></div>', unsafe_allow_html=True)
        ca, cb = st.columns(2, gap="large")
        with ca:
            st.markdown(_card_quality(), unsafe_allow_html=True)
        with cb:
            st.markdown(_card_bottom(), unsafe_allow_html=True)
        st.markdown(_card_size(), unsafe_allow_html=True)
        with st.container():
            st.markdown('<p class="mg-h" style="margin-top:16px">🎛️ Calcolatore — prova a muovere i tre fattori</p>', unsafe_allow_html=True)
            _calc_widget()
        st.markdown(
            '<div class="mg-note">⚠️ <b>Regime SHORT:</b> quando la Bussola ARGO è in discesa, '
            'il moltiplicatore regime (×0.3) taglia la size; se il risultato scende sotto l’1% la '
            'posizione viene <b>azzerata</b> e l’Entry Mode diventa “⛔ NON ENTRARE”. È la protezione '
            'che ti impedisce di accumulare contro tendenza. I titoli <b>manuali</b> che inserisci tu '
            'non ricevono alcuna size automatica: la size è calcolata solo sui risultati dello screening.</div>',
            unsafe_allow_html=True,
        )
