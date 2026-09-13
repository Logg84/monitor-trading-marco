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


def _call_gemini(system_prompt: str, user_prompt: str) -> dict:
    """Ritorna sempre {"ok": bool, "text": str}, mai un'eccezione non gestita."""
    api_key = _get_secret("GEMINI_API_KEY")
    if not api_key:
        return {"ok": False, "text": "GEMINI_API_KEY non configurata in secrets.toml."}

    model = _get_secret("GEMINI_MODEL", _DEFAULT_MODEL)
    url = f"{_API_BASE}/{model}:generateContent"
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 500},
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
