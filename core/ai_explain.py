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

import requests
import streamlit as st

_DEFAULT_MODEL = "gemini-flash-lite-latest"
_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_TIMEOUT = 25

DISCLAIMER = (
    "⚠️ Testo generato automaticamente da un modello linguistico a partire "
    "dai dati già calcolati dal portale. Non è un consiglio di investimento, "
    "verifica sempre i dati in tabella/grafico."
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


def explain_watchlist_row(ctx: dict) -> dict:
    """
    ctx: dati già calcolati per una riga Watchlist (vedi build_watchlist_ai_context
    in app.py per le chiavi esatte). Nessun dato viene ricalcolato o recuperato
    qui: solo formattato e passato al modello.
    """
    user_prompt = (
        "Spiega questa riga della mia Watchlist personale. Dati già calcolati "
        "dal portale (JSON):\n\n"
        f"{json.dumps(ctx, ensure_ascii=False, indent=2, default=str)}\n\n"
        "Copri in un unico paragrafo discorsivo: perché il titolo è in "
        "Watchlist (drawdown dal massimo + quali conferme Wyckoff/volumetriche "
        "ci sono), cosa segnala oggi di eventuale nuovo (se Segnale è attivo, "
        "specifica anche se l'origine è classica o legata a una candela "
        "Sifrediana recente/odierna, senza però consigliare nulla), e cosa "
        "tenere d'occhio (zona di prezzo/livelli vicini, eventuale trimestrale "
        "imminente, nota di settore se presente)."
    )
    return _call_gemini(_BASE_SYSTEM_PROMPT, user_prompt)


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
