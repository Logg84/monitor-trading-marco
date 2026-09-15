"""
Livello di spiegazione AI (Google Gemini) per Watchlist, COT e Regime.

Principio fermo: il modello NON tocca mai Segnale/punteggi (restano 100%
deterministici) e non accede mai a fonti esterne (yfinance/CFTC/news). Riceve
SOLO dati già calcolati dal portale e li traduce in prosa per un utente che
non vuole leggere ogni singola colonna/tabella. Non genera mai indicazioni
operative (comprare/vendere/target consigliato) — è un portale pubblico.

Chiamata via REST (nessuna dipendenza nuova, requests è già in requirements).
Chiave in .streamlit/secrets.toml come GEMINI_API_KEY (stesso pattern di
FDA_API_KEY). Modello di default via alias "gemini-flash-lite-latest" (si
aggiorna da solo, evita di restare ancorati a una versione che Google
deprecare); override possibile con GEMINI_MODEL in secrets.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

_DEFAULT_MODEL = "gemini-flash-lite-latest"
_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_TIMEOUT = 25

# Soglia minima di trade chiusi prima di re-iniettare statistiche nel prompt:
# stessa soglia già decisa per non toccare lo scoring (sessione del 13/09).
_MIN_CLOSED_FOR_LEARNING = 15
_SIMULATION_CSV = Path(__file__).resolve().parent.parent / "data" / "simulazione_trades.csv"

DISCLAIMER = (
    "⚠️ Testo generato automaticamente da un modello linguistico a partire "
    "dai dati già calcolati dal portale. È una lettura tecnica motivata, "
    "NON un consiglio di investimento né un ordine di acquisto/vendita: "
    "verifica sempre i dati in tabella/grafico e decidi in autonomia."
)

_BASE_SYSTEM_PROMPT = """Sei un assistente che spiega in italiano, in prosa semplice e discorsiva, dati di analisi tecnica/quantitativa già calcolati da un portale di monitoraggio personale (metodologia Wyckoff, flussi istituzionali, COT). Regole assolute, da rispettare sempre:
1. Usa SOLO i dati forniti nel messaggio utente. Non inventare numeri, notizie, eventi o cause, non presumere di avere accesso a fonti esterne o dati più recenti.
2. Non dare MAI indicazioni operative: niente "compra", "vendi", "conviene entrare/uscire", "target di prezzo consigliato", "buon punto di ingresso". Descrivi solo cosa dicono i dati forniti, senza tradurli in un consiglio.
3. Non fare previsioni o proiezioni statistiche non direttamente supportate dai numeri forniti.
4. Se i dati sono contraddittori, incompleti o ambigui, dillo esplicitamente invece di forzare una lettura coerente.
5. Risposta breve: 4-6 frasi in un unico paragrafo discorsivo, tono tecnico ma comprensibile, niente elenchi puntati, niente titoli/markdown."""


def _get_secret(name: str, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


def _closed_trades_learning_note(min_closed: int = _MIN_CLOSED_FOR_LEARNING) -> str | None:
    """
    Legge data/simulazione_trades.csv (unica fonte di verità sugli esiti,
    già scritta da core/simulazione_engine.py — nessun file parallelo).
    Sotto soglia ritorna None: niente statistiche premature nel prompt,
    stessa soglia già decisa in sessione (13/09) per non toccare lo scoring.
    """
    if not _SIMULATION_CSV.exists():
        return None
    try:
        df = pd.read_csv(_SIMULATION_CSV)
    except Exception:
        return None
    closed = df[df.get("Stato") == "Chiuso"].copy()
    if len(closed) < min_closed:
        return None

    closed["_win"] = closed["Motivo_Uscita"].astype(str).str.contains("Take Profit", na=False)
    n = len(closed)
    win_rate = round(100 * closed["_win"].mean(), 1)

    factor_lines = []
    if "Origine_Segnale" in closed.columns:
        by_origine = closed.groupby("Origine_Segnale")["_win"].agg(["mean", "count"])
        by_origine = by_origine[by_origine["count"] >= 3]
        if len(by_origine) >= 2:
            best = by_origine["mean"].idxmax()
            worst = by_origine["mean"].idxmin()
            if best != worst:
                factor_lines.append(
                    f"i trade con origine '{best}' hanno un win rate più alto "
                    f"({round(100 * by_origine.loc[best, 'mean'], 1)}%, "
                    f"n={int(by_origine.loc[best, 'count'])}) rispetto a "
                    f"'{worst}' ({round(100 * by_origine.loc[worst, 'mean'], 1)}%, "
                    f"n={int(by_origine.loc[worst, 'count'])})"
                )
    if "Score_Alert" in closed.columns:
        high = closed[closed["Score_Alert"] >= 5]
        low = closed[closed["Score_Alert"] < 5]
        if len(high) >= 3 and len(low) >= 3:
            wr_high = round(100 * high["_win"].mean(), 1)
            wr_low = round(100 * low["_win"].mean(), 1)
            if abs(wr_high - wr_low) >= 10:
                factor_lines.append(
                    f"i trade con punteggio alert ≥5 hanno win rate {wr_high}% "
                    f"contro {wr_low}% per quelli <5"
                )

    note = f"{n} trade chiusi in simulazione, win rate {win_rate}%."
    if factor_lines:
        note += " " + "; ".join(factor_lines) + "."
    return note


def _call_gemini(system_prompt: str, user_prompt: str, max_tokens: int = 500) -> dict:
    """Ritorna sempre {"ok": bool, "text": str}, mai un'eccezione non gestita."""
    api_key = _get_secret("GEMINI_API_KEY")
    if not api_key:
        return {"ok": False, "text": "GEMINI_API_KEY non configurata in secrets.toml."}

    model = _get_secret("GEMINI_MODEL", _DEFAULT_MODEL)
    url = f"{_API_BASE}/{model}:generateContent"
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": max_tokens},
    }
    try:
        resp = requests.post(url, params={"key": api_key}, json=payload, timeout=_TIMEOUT)
    except requests.RequestException as exc:
        return {"ok": False, "text": f"Errore di rete verso Gemini: {exc}"}

    if resp.status_code == 429:
        return {"ok": False, "text": "Limite di richieste Gemini raggiunto per ora, riprova tra qualche minuto."}
    if resp.status_code != 200:
        return {"ok": False, "text": f"Errore Gemini ({resp.status_code}): {resp.text[:200]}"}

    try:
        data = resp.json()
        cand = data["candidates"][0]
        if cand.get("finishReason") == "SAFETY":
            return {"ok": False, "text": "Risposta bloccata dai filtri di sicurezza di Gemini."}
        parts = cand["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError, ValueError):
        return {"ok": False, "text": "Risposta Gemini in un formato inatteso."}

    if not text:
        return {"ok": False, "text": "Gemini ha risposto senza contenuto."}
    return {"ok": True, "text": text}


_WATCHLIST_ROW_SYSTEM_PROMPT = """Sei un analista tecnico che dà una lettura di SINTESI assertiva, in italiano, di un singolo titolo della Watchlist di un portale di monitoraggio personale (metodologia Wyckoff, flussi istituzionali, forza di settore, RSI). L'utente ha già tutti i numeri sotto gli occhi in tabella e grafico: il tuo valore aggiunto NON è ripeterli, ma combinarli in un giudizio tecnico chiaro, con un ragionamento esplicito.

Regole assolute, da rispettare sempre:
1. Usa SOLO i dati forniti nel messaggio utente (inclusi eventuali livelli SL/TP o zone già calcolati dal portale). Non inventare numeri, notizie, eventi o cause, non presumere di avere accesso a fonti esterne o dati più recenti. Se serve citare un livello di prezzo, usa solo quelli già presenti nei dati forniti — non calcolarne di tuoi.
2. Esprimi una lettura direzionale chiara (es. "il quadro è orientato al rialzo nel breve" oppure "la spinta sembra in esaurimento") con il ragionamento che la sostiene. Non formulare MAI un invito esplicito all'azione ("compra ora", "vendi ora", "entra qui"): la conclusione è una lettura tecnica motivata, non un ordine impartito all'utente.
3. Accanto alla lettura, dai SEMPRE anche la controprova: cosa la invaliderebbe o la renderebbe meno solida (es. rottura di un livello già nei dati, mancanza di conferma volumetrica, pattern Wyckoff incompleto). Bilancia l'assertività della conclusione con onestà sui suoi limiti — questa è la parte di valore della risposta, non un'aggiunta facoltativa.
4. Evidenzia le tensioni o le conferme tra segnali (settore, RSI, Wyckoff, zone/livelli, Segnale attivo): es. settore forte + RSI in salita ma Wyckoff basso/pattern non completo → slancio probabilmente di breve respiro con rischio di ritracciamento prima di un movimento più esteso.
5. Se ricevi una nota di apprendimento storico (statistiche su trade chiusi reali), usala per calibrare quanto essere assertivo — non citarla meccanicamente come una statistica a sé, integrala nel ragionamento.
6. Se i dati sono insufficienti per una lettura di sintesi, dillo esplicitamente invece di forzarla.
7. Risposta diretta: 4-6 frasi in un unico paragrafo, tono da analista tecnico esperto che si sbilancia ma argomenta, niente elenchi puntati, niente markdown, niente preamboli tipo "i dati mostrano che" — vai dritto al punto di vista."""


def explain_watchlist_row(ctx: dict) -> dict:
    """
    ctx: dati già calcolati per una riga Watchlist (vedi build_watchlist_ai_context
    in app.py per le chiavi esatte). Nessun dato viene ricalcolato o recuperato
    qui: solo formattato e passato al modello, che ne restituisce una lettura
    di sintesi assertiva (direzione + ragionamento + controprova), mai una
    descrizione riga per riga né prezzi/target inventati.
    """
    system_prompt = _WATCHLIST_ROW_SYSTEM_PROMPT
    learning_note = _closed_trades_learning_note()
    if learning_note:
        system_prompt += (
            "\n\nNota di apprendimento storico (trade reali chiusi in "
            f"simulazione, aggiornata automaticamente): {learning_note}"
        )
    user_prompt = (
        "Dammi una lettura tecnica di sintesi assertiva (non una descrizione "
        "dato per dato) di questo titolo della mia Watchlist personale, in "
        "ottica Wyckoff/di portale. Dati già calcolati (JSON):\n\n"
        f"{json.dumps(ctx, ensure_ascii=False, indent=2, default=str)}\n\n"
        "Dammi: (a) la direzione/fase più probabile secondo i segnali "
        "disponibili e perché, (b) la controprova — cosa la invaliderebbe."
    )
    return _call_gemini(system_prompt, user_prompt)


# ────────────────────────────────────────────────────────────────
# Watchlist — riassunto aggregato (invece della singola riga)
# ────────────────────────────────────────────────────────────────
_WATCHLIST_DIGEST_SYSTEM_PROMPT = _BASE_SYSTEM_PROMPT + """

Regole aggiuntive per il riassunto aggregato di più titoli in Watchlist:
6. Riceverai una LISTA di titoli, ciascuno con gli stessi dati già descritti sopra. Il tuo compito è trovare pattern, raggruppamenti e cose degne di nota TRA i titoli, non ripetere una spiegazione per ognuno.
7. Non stilare una classifica tua e non insinuare quale titolo sia "il migliore" o "da guardare per primo": l'ordine di priorità è già deciso dal punteggio Bottom/Priorità calcolato dal portale, tu lo citi se utile ma non lo rifai.
8. Struttura la risposta in 3-4 brevi paragrafi separati da una riga vuota (niente elenchi puntati, niente titoli/markdown): (a) quadro generale — quanti titoli, quanti con un Segnale attivo oggi e di che origine; (b) eventuali cluster ricorrenti (stesso settore/sotto-settore, stessa nota settoriale, flag Wyckoff comuni); (c) titoli con qualcosa di particolare da segnalare (badge Squeeze, trimestrale imminente, Sifrediana odierna, livelli manuali vicini); (d) se rilevante, dati mancanti o incoerenti che limitano la lettura.
9. Se la lista è vuota o ha un solo titolo, dillo in una frase sola invece di forzare una sintesi."""


def explain_watchlist_digest(entries: list[dict]) -> dict:
    """
    entries: lista di dict, uno per titolo in Watchlist, con la stessa forma
    usata da explain_watchlist_row (vedi build in app.py). Restituisce un
    'unico riassunto per l'intera lista, non una spiegazione per riga.
    """
    if not entries:
        return {"ok": True, "text": "Nessun titolo in Watchlist al momento."}
    user_prompt = (
        f"Riassumi questi {len(entries)} titoli della mia Watchlist personale. "
        "Dati già calcolati dal portale, uno per titolo (JSON):\n\n"
        f"{json.dumps(entries, ensure_ascii=False, indent=2, default=str)}"
    )
    return _call_gemini(_WATCHLIST_DIGEST_SYSTEM_PROMPT, user_prompt, max_tokens=900)


# ────────────────────────────────────────────────────────────────
# COT — regole aggiuntive da docs/COT-LETTURE.md, obbligatorie per
# evitare le letture sbagliate ma intuitive (segno grezzo, "commercials
# = smart money", swap dealer come opinione anziché flusso meccanico).
# ────────────────────────────────────────────────────────────────
_COT_SYSTEM_PROMPT = _BASE_SYSTEM_PROMPT + """

Regole aggiuntive obbligatorie per i dati COT (Commitments of Traders):
6. Il segno grezzo del net Producer/Merchant NON è una previsione: conta solo il percentile storico di quel mercato specifico e la direzione del cambiamento (già forniti nei dati come "pP"/"dP" o "pBase"/"pQuote"). Non dedurre mai "producer long = si copre da un ribasso": è quasi sempre il contrario (chi deve comprare fisico blocca i costi, o chi era coperto sta ricoprendo).
7. Lo Swap Dealer non esprime mai una view di mercato: il suo netto è la conseguenza meccanica del book clienti OTC. Non trattarlo mai come "opinione" o "previsione" — solo come flusso (afflusso/deflusso), e solo il cambiamento conta, non il livello assoluto.
8. "Commercials = smart money" è un mito esplicitamente sbagliato: non riprodurlo mai, nemmeno come sfumatura.
9. I campi che nei dati forniti contengono già un testo interpretativo (chiavi come "txt", "incentivo", "conferma") sono letture GIÀ corrette prodotte dal portale secondo le regole CFTC ufficiali: usale come base per la sintesi, non proporre una lettura diversa o in contraddizione con esse.
10. Le divergenze (tipi COP-/COP+/CARB-/CARB+, se presenti nei dati) hanno una definizione tecnica precisa: descrivile così come sono etichettate, senza reinterpretarle liberamente."""


def explain_cot_market(ctx: dict) -> dict:
    """
    ctx: dati già calcolati per un singolo mercato commodity (percentili,
    derivate, output di comm_state/producer_lettura/swap_lettura/divergenze).
    """
    user_prompt = (
        "Spiega la situazione COT di questo mercato materie prime. Dati già "
        "calcolati dal portale, incluse le letture corrette di Producer e "
        "Swap Dealer (JSON):\n\n"
        f"{json.dumps(ctx, ensure_ascii=False, indent=2, default=str)}\n\n"
        "Sintetizza in un unico paragrafo discorsivo: cosa dice insieme il "
        "posizionamento di Producer/Merchant, Managed Money e Swap Dealer "
        "(stato complessivo), quanto è marcato o estremo rispetto alla "
        "storia di questo mercato, ed eventuali zone di divergenza recenti "
        "tra prezzo e posizionamento se presenti nei dati. Nessuna previsione "
        "di prezzo, nessun consiglio operativo."
    )
    return _call_gemini(_COT_SYSTEM_PROMPT, user_prompt)


def explain_cot_fx(ctx: dict) -> dict:
    """
    ctx: quadro forex già calcolato (squilibri estremi, coppie affollate,
    coppie allineate, primi segnali di divergenza traiettorie).
    """
    user_prompt = (
        "Spiega il quadro COT forex di oggi. Dati già calcolati dal portale "
        "(JSON):\n\n"
        f"{json.dumps(ctx, ensure_ascii=False, indent=2, default=str)}\n\n"
        "Sintetizza in un unico paragrafo discorsivo: quali coppie mostrano "
        "lo squilibrio di posizionamento più marcato e in che verso, quali "
        "coppie sono 'affollate' (entrambe le gambe estreme nella stessa "
        "direzione, quindi il segnale sulla coppia si annulla anche se dice "
        "molto sulle singole valute), e se ci sono primi segnali di "
        "divergenza di traiettoria da monitorare. Nessuna previsione di "
        "prezzo, nessun consiglio operativo."
    )
    return _call_gemini(_COT_SYSTEM_PROMPT, user_prompt)


# ────────────────────────────────────────────────────────────────
# Regime (Bussola di mercato)
# ────────────────────────────────────────────────────────────────
_REGIME_SYSTEM_PROMPT = _BASE_SYSTEM_PROMPT + """

Regola aggiuntiva per la Bussola di mercato (Regime):
6. Identifica quali attori pesano di più nella direzione del composite attuale usando il campo "contributo_ponderato" già calcolato nei dati (non ricalcolarlo tu). Se un attore ha "source" uguale a "no data" o "COT assente", è escluso dal calcolo: menzionalo solo se rilevante per capire perché mancano informazioni. Non trasformare mai il regime (LONG/SHORT/NEUTRO) in un consiglio di acquisto/vendita: è solo un moltiplicatore di dimensione di posizione che l'utente applica secondo le proprie regole, non un'indicazione operativa."""


def explain_regime(ctx: dict) -> dict:
    """
    ctx: composite, regime e lista attori (con score/source/detail/peso/
    contributo_ponderato già calcolati) da core.regime.compute_regime().
    """
    user_prompt = (
        "Spiega il regime di mercato attuale. Dati già calcolati dal "
        "portale (JSON):\n\n"
        f"{json.dumps(ctx, ensure_ascii=False, indent=2, default=str)}\n\n"
        "Sintetizza in un unico paragrafo discorsivo: cosa dice il "
        "composite (regime attuale), quali attori pesano di più in quella "
        "direzione e quali invece vanno in senso opposto o sono neutri, "
        "e se ci sono attori senza dati che limitano l'affidabilità della "
        "lettura in questo momento."
    )
    return _call_gemini(_REGIME_SYSTEM_PROMPT, user_prompt)
