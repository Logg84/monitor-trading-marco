"""
Motore lettura immagini (grafici) — UNICO provider: Groq (il più veloce).
Non critico: se manca la chiave o l'API fallisce, si passa alla lettura manuale.
Chiave env: GROQ_API_KEY. Nessuna dipendenza nuova: solo requests.
"""
from __future__ import annotations

import base64
import json
import os

import requests

DEFAULT_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

SYSTEM_PROMPT = (
    "Sei un assistente di lettura grafica per un operatore di medio-lungo periodo. "
    "Fai SOLO lettura tecnica descrittiva, mai consigli di investimento o ordini. "
    "Se un elemento non è leggibile, dichiaralo. Rispondi SEMPRE con JSON valido."
)

USER_PROMPT = (
    "Leggi questo grafico (prezzo + eventuali volumi) e restituisci un JSON con queste chiavi:\n"
    "- trend_breve: stringa (es. 'ribassista', 'laterale', 'rimbalzo')\n"
    "- trend_medio: stringa\n"
    "- livelli_chiave: lista di stringhe descrittive (supporti/resistenze visibili)\n"
    "- zona_volumi: stringa (eventuale area di accumulazione/distribuzione visibile)\n"
    "- prezzo_vs_vwap: stringa (se la linea media è distinguibile)\n"
    "- incoerenze: stringa (elementi che contraddicono la lettura)\n"
    "- sintesi: stringa, massimo 3 righe, solo descrizione, nessun consiglio.\n"
    "Niente altro testo fuori dal JSON."
)

def _parse_json(text: str) -> dict | None:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.startswith("json"):
            t = t[4:]
    try:
        return json.loads(t)
    except Exception:
        start = t.find("{")
        end = t.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(t[start:end + 1])
            except Exception:
                return None
    return None

def read_chart(image_bytes: bytes, mime: str = "image/png",
               model: str | None = None, timeout: int = 60) -> dict:
    """
    Legge uno screenshot di grafico via Groq.
    Ritorna {"provider", "model", "json", "text"}.
    Solleva eccezioni se la chiave manca o la chiamata fallisce
    (il chiamante passa alla lettura manuale).
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY non configurata")

    mdl = model or os.getenv("VISION_MODEL") or DEFAULT_MODEL
    b64 = base64.b64encode(image_bytes).decode()

    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
        json={
            "model": mdl,
            "temperature": 0.2,
            "max_tokens": 800,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": USER_PROMPT},
                    {"type": "image_url",
                     "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ]},
            ],
        },
        timeout=timeout,
    )
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"]
    return {"provider": "groq", "model": mdl,
            "json": _parse_json(text), "text": text}
