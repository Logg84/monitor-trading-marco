import streamlit as st

_METRIC_GUIDE_CSS = """
<style>
/* === Container metric guide === */
.mg-wrap {
  font-family: 'Inter', sans-serif;
  color: var(--txt-2, #cbd5e1);
  font-size: 12.5px;
  line-height: 1.6;
}

/* === Sezione (card) === */
.mg-section {
  background: linear-gradient(135deg, #0f172a 0%, #111827 100%);
  border: 1px solid var(--border, #1e293b);
  border-left: 4px solid var(--accent, #38bdf8);
  border-radius: 10px;
  padding: 14px 18px;
  margin-bottom: 14px;
  transition: border-color .2s ease, box-shadow .2s ease;
}
.mg-section:hover {
  border-left-color: #38bdf8;
  box-shadow: 0 6px 20px -12px rgba(56,189,248,.4);
}
.mg-section.green  { border-left-color: #22c55e; }
.mg-section.yellow { border-left-color: #f59e0b; }
.mg-section.red    { border-left-color: #ef4444; }
.mg-section.violet { border-left-color: #a78bfa; }

/* === Titolo sezione === */
.mg-title {
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 700;
  font-size: 14px;
  color: var(--txt-1, #f8fafc);
  margin: 0 0 8px 0;
  display: flex;
  align-items: center;
  gap: 8px;
  letter-spacing: -0.01em;
}
.mg-title .pill {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 2px 7px;
  border-radius: 5px;
  background: rgba(56,189,248,0.12);
  color: #38bdf8;
  border: 1px solid rgba(56,189,248,0.3);
}

/* === Corpo === */
.mg-body {
  color: var(--txt-2, #cbd5e1);
  font-size: 12.5px;
  line-height: 1.65;
}
.mg-body b, .mg-body strong { color: var(--txt-1, #f8fafc); font-weight: 600; }
.mg-body code, .mg-body .mono {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11.5px;
  color: #7dd3fc;
  background: rgba(56,189,248,0.08);
  padding: 1px 5px;
  border-radius: 4px;
}

/* === Lista criteri === */
.mg-criteria {
  list-style: none;
  padding: 0;
  margin: 8px 0 12px 0;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 6px;
}
.mg-criteria li {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11.5px;
  color: var(--txt-2, #cbd5e1);
  padding: 6px 10px;
  background: rgba(15,23,42,0.5);
  border: 1px solid var(--border, #1e293b);
  border-radius: 6px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.mg-criteria li::before {
  content: "▸";
  color: var(--accent, #38bdf8);
  font-weight: 700;
}

/* === Tabelle === */
.mg-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--border, #1e293b);
  border-radius: 8px;
  margin: 10px 0;
}
.mg-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.mg-table thead th {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--txt-muted, #64748b);
  background: #0b1220;
  padding: 9px 12px;
  text-align: left;
  border-bottom: 1px solid var(--border-strong, #334155);
}
.mg-table tbody td {
  padding: 9px 12px;
  border-bottom: 1px solid rgba(30,41,59,0.5);
  color: var(--txt-2, #cbd5e1);
  vertical-align: middle;
}
.mg-table tbody tr:last-child td { border-bottom: none; }
.mg-table tbody tr:nth-child(even) td { background: rgba(255,255,255,0.015); }
.mg-table tbody tr:hover td { background: rgba(56,189,248,0.06); }
.mg-table .score {
  font-family: 'IBM Plex Mono', monospace;
  font-weight: 700;
  text-align: center;
}
.mg-table .icon {
  font-size: 15px;
  text-align: center;
}

/* === Note a piè di sezione === */
.mg-note {
  font-size: 11px;
  color: var(--txt-muted, #64748b);
  font-style: italic;
  margin-top: 8px;
  padding-left: 10px;
  border-left: 2px solid var(--border-strong, #334155);
}
.mg-note b { color: var(--txt-3, #94a3b8); }

/* === Footer disclaimer === */
.mg-disclaimer {
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.3);
  border-left: 3px solid #f59e0b;
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 11.5px;
  color: #fcd34d;
  margin-top: 6px;
  font-family: 'Inter', sans-serif;
}
.mg-disclaimer b { color: #fef3c7; }

/* === Colonne lista === */
.mg-cols {
  list-style: none;
  padding: 0;
  margin: 8px 0;
}
.mg-cols li {
  padding: 7px 10px;
  border-bottom: 1px solid rgba(30,41,59,0.4);
  font-size: 12px;
}
.mg-cols li:last-child { border-bottom: none; }
.mg-cols li b {
  font-family: 'IBM Plex Mono', monospace;
  color: var(--txt-1, #f8fafc);
  font-weight: 600;
  font-size: 11.5px;
}

/* === Punteggio inline === */
.mg-pill-score {
  display: inline-block;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10.5px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 5px;
  margin-right: 6px;
  vertical-align: middle;
}
.mg-pill-score.solid   { background: rgba(34,197,94,0.15); color: #86efac; border: 1px solid rgba(34,197,94,0.35); }
.mg-pill-score.warn    { background: rgba(245,158,11,0.15); color: #fcd34d; border: 1px solid rgba(245,158,11,0.35); }
.mg-pill-score.fragile { background: rgba(239,68,68,0.15); color: #fca5a5; border: 1px solid rgba(239,68,68,0.35); }
</style>
"""


def render_metric_guide():
    """
    Guida rapida alle metriche della tabella screening.
    Richiamata in coda al pannello automazione, prima delle tabelle.
    """
    st.markdown(_METRIC_GUIDE_CSS, unsafe_allow_html=True)

    with st.expander("📘 Guida alle metriche — Health · Bottom · Size (apri per spiegare una colonna)", expanded=False):
        st.markdown("""
<div class="mg-wrap">

### 🩺 Health Check (0‑4) – Salute finanziaria assoluta
<div class="mg-section">
<div class="mg-title">Health Check <span class="pill">0-4 punti</span></div>
<div class="mg-body">
Valuta la solidità dell’azienda <b>in sé</b>, senza confronti con altre.

<ul class="mg-criteria">
  <li><b>FCF &gt; 0</b> → genera cassa operativa</li>
  <li><b>Crescita Ricavi YoY &gt; 0</b> → fatturato in espansione</li>
  <li><b>Utile Netto &gt; 0</b> → redditività positiva</li>
  <li><b>D/E &lt; 1.5</b> → indebitamento contenuto</li>
</ul>

<div class="mg-table-wrap"><table class="mg-table">
<thead><tr><th class="score">Punteggio</th><th class="icon">Stato</th><th>Significato</th></tr></thead>
<tbody>
  <tr><td class="score">4/4</td><td class="icon">✅</td><td>Tutti i criteri superati – <b>azienda solida</b></td></tr>
  <tr><td class="score">2‑3/4</td><td class="icon">⚠️</td><td>Qualche debolezza – attenzione</td></tr>
  <tr><td class="score">0‑1/4</td><td class="icon">❌</td><td>Criteri largamente non soddisfatti – <b>fragile</b></td></tr>
</tbody></table></div>

<div class="mg-note">
  <b>Nota mercati europei:</b> le small cap europee possono mostrare fisiologicamente D/E più elevati o FCF negativo per investimenti. Un punteggio di 2‑3/4 ⚠️ in questi casi non è di per sé un segnale di debolezza: va letto nel contesto della capitalizzazione e del settore.
</div>

<div class="mg-note">
  <b>Sorgente dati:</b> Yahoo Finance, aggiornati ogni 14 giorni.
</div>
</div></div>

---

### 📉 Bottom Score (0‑4) – Segnali di inversione tecnica
<div class="mg-section yellow">
<div class="mg-title">Bottom Score <span class="pill">semaforo inversione</span></div>
<div class="mg-body">
Indica se il titolo sta mostrando <b>segnali di esaurimento della discesa</b>:

<ul class="mg-criteria">
  <li>Decelerazione del <b>Rate of Change (ROC)</b></li>
  <li><b>MACD Histogram</b> in risalita</li>
  <li>Vicinanza a un <b>POC strutturale</b> con momentum rialzista</li>
  <li>Convergenza di più <b>VWAP</b></li>
  <li>Aumento di <b>volume</b> e <b>Force Index</b></li>
</ul>

<div class="mg-table-wrap"><table class="mg-table">
<thead><tr><th class="score">Punteggio</th><th class="icon">Semaforo</th><th>Significato</th></tr></thead>
<tbody>
  <tr><td class="score">4</td><td class="icon">🟢</td><td><b>Forte inversione</b> – pronto per l’ingresso</td></tr>
  <tr><td class="score">3</td><td class="icon">🟡</td><td>Segnali iniziali – monitorare</td></tr>
  <tr><td class="score">2</td><td class="icon">🟡</td><td>Esaurimento vendita – pazienza</td></tr>
  <tr><td class="score">0‑1</td><td class="icon">🔴</td><td><b>Nessuna inversione</b> – non entrare</td></tr>
</tbody></table></div>
</div></div>

---

### 💰 Size Suggerita (%) – Dimensione operativa
<div class="mg-section green">
<div class="mg-title">Size Suggerita <span class="pill">riferimento %</span></div>
<div class="mg-body">
È un <b>riferimento di posizionamento</b>, non un ordine. Combina:

<ul class="mg-cols">
  <li><b>Capitalizzazione</b> → base della size</li>
  <li><b>Health Check</b> → moltiplicatore: <span class="mono">×1.2</span> se ≥3, <span class="mono">×0.6</span> se ≤1</li>
  <li><b>Bias Bussola ARGO</b> → <span class="mono">×0.3</span> in SHORT, <span class="mono">×0.6</span> in NEUTRO, <span class="mono">×1.0</span> in LONG</li>
  <li>Valori inferiori a 1% vengono azzerati (<span class="mono">size = 0</span>)</li>
</ul>

<div class="mg-note">
  La size è puramente indicativa e va adattata al tuo money management.
</div>
</div></div>

---

### 📊 Altre colonne della tabella
<div class="mg-section violet">
<div class="mg-title">Colonne ausiliarie <span class="pill">tabella screening</span></div>
<div class="mg-body">
<ul class="mg-cols">
  <li><b>Drawdown %</b> — distanza dal massimo storico (ATH). Più è negativo, più il titolo è “in sconto”.</li>
  <li><b>POC più vicino / dPOC%</b> — POC operativo e distanza percentuale attuale. <span class="mono">📍 in zona</span> se il prezzo è dentro l’area del POC.</li>
  <li><b>VWAP vicino / dVWAP%</b> — il VWAP (3M/1Y/4Y) più prossimo al prezzo e la relativa distanza.</li>
  <li><b>🎯 Alert</b> — compare solo se il prezzo tocca un POC o un VWAP entro la soglia configurata in sidebar.</li>
  <li><b>Operazione Potenziale</b> — lettura automatica del metodo REA basata su distanza dal POC e regime. <b>Non è un consiglio</b>: decisione e rischio sono interamente a carico dell’utente.</li>
  <li><b>Stato</b> — <span class="mono">Active</span> (in forte sconto), <span class="mono">Ripartito</span> (uscito dallo sconto), <span class="mono">Nuovo</span> (prima apparizione).</li>
</ul>
</div></div>

<div class="mg-disclaimer">
  ⚖️ <b>Disclaimer:</b> tutte le metriche e le letture di ARGO sono strumenti di analisi, non consigli d’investimento. Ogni decisione operativa e il relativo rischio sono interamente a carico dell’utente.
</div>

</div>
""", unsafe_allow_html=True)
