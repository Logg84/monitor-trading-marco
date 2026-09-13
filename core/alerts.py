"""
Integrazione Telegram e Gestione Alert per Monitor Trading Marco.

Gestisce invio notifiche Telegram, day_lock di 5 giorni (solo a invio
confermato) e generazione CSV per la pagina Simulazione.
"""
from __future__ import annotations

import json
import os
import re
import time
import datetime as _dt
from pathlib import Path
import pandas as pd
import requests
import streamlit as st
from core.data_engine import earnings_dates_list

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SENT_ALERTS_FILE = DATA_DIR / "sent_alerts.json"
REGIME_STATE_FILE = DATA_DIR / "regime_state.json"
REGIME_CONFIRM_RUNS = 2  # run consecutivi di alert_checker.py (ogni 2h) prima di notificare


# ── INVIO MESSAGGIO TELEGRAM ───────────────────────────────
def get_telegram_config() -> tuple[str | None, str | None]:
    token, chat_id = None, None
    try:
        if "telegram" in st.secrets:
            token = st.secrets["telegram"].get("bot_token")
            chat_id = st.secrets["telegram"].get("chat_id")
    except Exception:
        pass
    if not token:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not chat_id:
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    return token, chat_id


def send_telegram_message(message: str) -> bool:
    token, chat_id = get_telegram_config()
    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }

    time.sleep(1.0)
    for attempt in range(3):
        try:
            response = requests.post(url, json=payload, timeout=15)
            if response.status_code == 200:
                return True
            elif response.status_code == 429:
                try:
                    retry_after = response.json().get("parameters", {}).get("retry_after", 5)
                except Exception:
                    retry_after = 5
                time.sleep(retry_after + 1)
                continue
            else:
                return False
        except Exception:
            time.sleep(2)
    return False


send_telegram = send_telegram_message  # alias legacy


# ── PERSISTENZA ALERT ──────────────────────────────────────
def _load_sent_alerts() -> dict:
    if not SENT_ALERTS_FILE.exists():
        return {}
    try:
        return json.loads(SENT_ALERTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_sent_alerts(state: dict) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SENT_ALERTS_FILE.write_text(
            json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass


def _register_sent_alert(
    ticker: str,
    alert_type: str,
    price: float | None = None,
    score: int | None = None,
    origine_segnale: str | None = None,
) -> None:
    state = _load_sent_alerts()
    now = _dt.datetime.now()
    state[f"{ticker}:{alert_type}"] = {
        "date": str(_dt.date.today()),
        "ticker": ticker,
        "type": alert_type,
        "timestamp": now.isoformat(),
        "score": score,
        "origine_segnale": origine_segnale,
    }
    hist = state.get("history", [])
    hist.append({
        "ts": now.isoformat(),
        "ticker": ticker,
        "kind": alert_type,
        "price": price,
        "score": score,
        "origine_segnale": origine_segnale,
    })
    state["history"] = hist[-200:]
    _save_sent_alerts(state)


# ── Compat pubblica per le pagine UI ──
def load_alert_state() -> dict:
    return _load_sent_alerts()


def save_alert_state(state: dict) -> None:
    _save_sent_alerts(state)


# ── CAMBIO REGIME (dedup a stato, NON il day_lock a 5gg dei ticker) ────────
# Il Regime è globale (non per ticker) e va notificato solo quando cambia
# stato, non ad ogni run. Serve inoltre un minimo di isteresi: alcuni "attori"
# di compute_regime() usano prezzi live, quindi vicino alle soglie ±15 il
# composito potrebbe oscillare avanti e indietro nell'arco della giornata.
# Richiediamo REGIME_CONFIRM_RUNS run consecutivi con lo stesso nuovo regime
# prima di considerarlo "confermato" e generare il candidato di alert.
def _load_regime_state() -> dict:
    if not REGIME_STATE_FILE.exists():
        return {"last_notified": None, "pending": None, "pending_count": 0}
    try:
        return json.loads(REGIME_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"last_notified": None, "pending": None, "pending_count": 0}


def _save_regime_state(state: dict) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        REGIME_STATE_FILE.write_text(
            json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass


def check_regime_change(regime_result: dict) -> dict | None:
    """
    Da chiamare ad ogni run con l'output di compute_regime(). Aggiorna sempre
    il bookkeeping (pending/pending_count) su disco; ritorna un candidato di
    alert SOLO quando il nuovo regime è confermato per REGIME_CONFIRM_RUNS run
    consecutivi ed è diverso dall'ultimo notificato.
    NON marca last_notified: quello lo fa register_regime_notified(), da
    chiamare solo a invio Telegram riuscito — stesso principio del day_lock
    a 5gg già usato per gli alert per ticker.
    """
    current = regime_result.get("regime")
    if not current:
        return None
    state = _load_regime_state()
    candidate = None

    if current == state.get("last_notified"):
        state["pending"], state["pending_count"] = None, 0
    else:
        if current == state.get("pending"):
            state["pending_count"] = int(state.get("pending_count", 0)) + 1
        else:
            state["pending"], state["pending_count"] = current, 1

        if state["pending_count"] >= REGIME_CONFIRM_RUNS:
            prev = state.get("last_notified") or "n/d"
            composite = regime_result.get("composite", 0.0)
            messaggio = (
                f"🧭 *CAMBIO REGIME DI MERCATO* 🧭\n\n"
                f"La bussola è passata da *{prev}* a *{current}*.\n"
                f"▪️ *Punteggio composito:* {composite:+.1f}\n\n"
                f"ℹ️ _Il Regime modula la size delle posizioni, non è un "
                f"filtro di ingresso: non apre né chiude trade in "
                f"Simulazione automaticamente._"
            )
            candidate = {
                "ticker": None,
                "text": messaggio,
                "type": "REGIME_CHANGE",
                "price": None,
                "score": None,
                "regime": current,
            }

    _save_regime_state(state)
    return candidate


def register_regime_notified(regime: str) -> None:
    """Da chiamare solo dopo invio Telegram riuscito del cambio regime."""
    state = _load_regime_state()
    state["last_notified"] = regime
    state["pending"], state["pending_count"] = None, 0
    _save_regime_state(state)


# ── Helper punteggio ──
def _parse_segale_score(segnale: str) -> int | None:
    if not isinstance(segnale, str):
        return None
    match = re.search(r"(\d)/6", segnale)
    if match:
        try:
            return int(match.group(1))
        except Exception:
            return None
    return None


# ── COMPILAZIONE ALERT ─────────────────────────────────────
def compile_alerts(df_screening: pd.DataFrame) -> list[dict]:
    if df_screening is None or df_screening.empty:
        return []

    alerts = []
    for _, row in df_screening.iterrows():
        ticker = row["Ticker"]
        nome_asset = row["Nome"]
        prezzo = row["Prezzo"]
        dd = row.get("DD%", 0.0)
        rsi_val = row.get("RSI", 50.0)
        segnale = str(row.get("Segnale", "—"))
        wyk_val = row.get("Wyckoff", "—")

        sec_score = row.get("SectorScore")
        vento = row.get("Vento", "nd")
        if pd.notna(sec_score) and sec_score is not None:
            try:
                score_val = float(sec_score)
                if score_val >= 60:
                    andamento_settore = f"LONG 🟢 (Score: {score_val:.0f}/100)"
                elif score_val <= 40:
                    andamento_settore = f"SHORT 🔴 (Score: {score_val:.0f}/100)"
                else:
                    andamento_settore = f"NEUTRO 🟡 (Score: {score_val:.0f}/100)"
            except Exception:
                andamento_settore = "NEUTRO 🟡"
        else:
            if vento in ["buono", "favore"]:
                andamento_settore = "LONG 🟢"
            elif vento == "contro":
                andamento_settore = "SHORT 🔴"
            else:
                andamento_settore = "NEUTRO 🟡"

        # A. SIFREDIANA (CANDELONE)
        if row.get("Sifrediana_Today", False):
            messaggio = (
                f"🚨 *CANDELONA PER {ticker}* 🚨\n\n"
                f"Il titolo *{nome_asset}* ({ticker}) ha appena registrato "
                f"una candela Sifrediana di forza istituzionale!\n\n"
                f"▪️ *Prezzo di Chiusura:* {prezzo:.2f} $\n"
                f"▪️ *RSI Daily:* {rsi_val:.0f}\n"
                f"▪️ *Drawdown dall'ATH:* {dd:+.1f}%\n"
                f"▪️ *Fascia GICS:* {row.get('Settore', '—')} · {row.get('Sotto-settore', '—')}\n"
                f"▪️ *Andamento Settore:* {andamento_settore}\n"
                f"▪️ *Punteggio Wyckoff:* {wyk_val}\n\n"
                f"ℹ️ _Questo allarme è prioritario e indipendente dal Bottom Score del titolo!_\n"
                f"📈 Visualizza su TradingView"
            )
            alerts.append({
                "ticker": ticker,
                "text": messaggio,
                "type": "SIFREDIANA",
                "price": float(prezzo) if pd.notna(prezzo) else None,
                "score": None,
            })
            continue

        # B. SEGNALI REVERSAL
        if segnale.startswith(("🟡", "🟢")):
            alert_type = "REVERSAL_GREEN" if "🟢" in segnale else "REVERSAL_YELLOW"
            icona = "🟢" if "🟢" in segnale else "🟡"
            titolo = (
                "SEGNALE DI FORZA CONFERMATO"
                if "🟢" in segnale
                else "TITOLO INTERESSANTE RILEVATO"
            )
            messaggio = (
                f"{icona} *{titolo}* {icona}\n\n"
                f"Il radar quantitativo ha rilevato un segnale operativo "
                f"per *{nome_asset}* ({ticker})!\n\n"
                f"▪️ *Stato Segnale:* {segnale}\n"
                f"▪️ *Prezzo Corrente:* {prezzo:.2f} $\n"
                f"▪️ *Drawdown dall'ATH:* {dd:+.1f}%\n"
                f"▪️ *RSI Daily:* {rsi_val:.0f}\n"
                f"▪️ *Bottom Score:* {row.get('Bottom', 'n/d')}/100\n"
                f"▪️ *Fascia GICS:* {row.get('Settore', '—')} · {row.get('Sotto-settore', '—')}\n"
                f"▪️ *Andamento Settore:* {andamento_settore}\n"
                f"▪️ *Punteggio Wyckoff:* {wyk_val}\n\n"
                f"📈 Visualizza su TradingView"
            )
            score = _parse_segale_score(segnale)
            # origine_segnale calcolato in reversal_state() e propagato fin qui
            # nella colonna Origine_Segnale: "classico" (punti>=5) vs
            # "sifrediana_assistita" (soglia abbassata a punti>=4 grazie a una
            # Sifrediana recente). Il bypass "sifrediana_today" non arriva mai
            # qui: quel caso viene intercettato sopra come CANDELONA.
            origine_segnale = row.get("Origine_Segnale")
            alerts.append({
                "ticker": ticker,
                "text": messaggio,
                "type": alert_type,
                "price": float(prezzo) if pd.notna(prezzo) else None,
                "score": score,
                "origine_segnale": origine_segnale,
            })
    return alerts


def _level_alert_candidates(entries: list[dict], states: dict) -> list[dict]:
    out = []
    for e in entries:
        t = e["ticker"]
        s = states.get(t) or {}
        price, prev = s.get("price"), s.get("prev_close")
        levels = e.get("levels") or {}
        if price is None or prev is None or not levels:
            continue
        for lname, lval in levels.items():
            if not lval or lval <= 0:
                continue
            is_res = lname == "L3"
            crossed = (
                (price >= lval and prev < lval)
                if is_res
                else (price <= lval and prev > lval)
            )
            if not crossed:
                continue
            verso = (
                "superato al rialzo (resistenza)"
                if is_res
                else "rotto al ribasso (supporto)"
            )
            messaggio = (
                f"🎯 *LIVELLO {lname} {'RAGGIUNTO' if is_res else 'ROTTO'}* — {t}\n\n"
                f"*{s.get('nome', t)}* ({t}) ha {verso}: "
                f"prezzo {price:.2f}, livello {lname} = {lval:.2f}.\n"
                f"📈 Visualizza su TradingView"
            )
            out.append({
                "ticker": t,
                "text": messaggio,
                "type": f"LIVELLO_{lname}",
                "price": price,
                "score": None,
            })
    return out


def _earnings_alert_candidates(entries: list[dict], states: dict, warn_days: int = 3) -> list[dict]:
    """
    Avviso trimestrale imminente per TUTTI i ticker in Watchlist (nessun
    filtro sul Segnale attivo).
    Dedup: nessuno stato dedicato, riusa il day_lock a 5gg già esistente sulla
    chiave "ticker:TRIMESTRALE_IMMINENTE" (stesso meccanismo di REVERSAL/
    LIVELLO). Basta perché la finestra di preavviso (3gg) è più corta della
    finestra di lock (5gg): il primo giorno utile in cui scatta blocca anche
    tutti i giorni successivi fino e oltre la trimestrale stessa.
    """
    out = []
    oggi = _dt.date.today()
    for e in entries or []:
        t = e["ticker"]
        s = (states or {}).get(t) or {}
        try:
            dates = earnings_dates_list(t)
        except Exception:
            continue
        if not dates:
            continue
        future = [d.date() for d in dates if d.date() >= oggi]
        if not future:
            continue
        next_date = min(future)
        days_to = (next_date - oggi).days
        if days_to > warn_days:
            continue
        quando = "oggi" if days_to == 0 else f"tra {days_to}gg ({next_date.strftime('%d/%m')})"
        segnale = str(s.get("segnale", "—"))
        messaggio = (
            f"⚠️ *TRIMESTRALE IMMINENTE* — {t}\n\n"
            f"*{s.get('nome', t)}* ({t}) riporta {quando}.\n"
            f"Segnale attuale: {segnale}\n\n"
            f"ℹ️ _Valuta di evitare ingressi impulsivi a poche ore dal "
            f"rilascio: il movimento post-earnings è spesso rumore, non "
            f"direzione._"
        )
        out.append({
            "ticker": t,
            "text": messaggio,
            "type": "TRIMESTRALE_IMMINENTE",
            "price": s.get("price"),
            "score": None,
        })
    return out


# ── ENTRY POINT PRINCIPALE ─────────────────────────────────
# NOTA: l'apertura trade di Simulazione è gestita ESCLUSIVAMENTE da
# core/simulazione_engine.py (run_simulation → open_trade), che calcola SL
# sul minimo settimanale reale e TP1-4 scalati. In precedenza esisteva qui
# una _aggiungi_trade_simulazione() con SL/TP fissi (-8%/+15%) chiamata da
# scripts/alert_checker.py PRIMA di simulazione_engine.py nello stesso
# workflow: apriva il trade con quei valori semplificati, dopodiché
# simulazione_engine.py trovava il ticker già "Aperto" e saltava — quindi
# i trade reali nascevano tutti dal percorso rozzo, mai da quello corretto.
# Rimossa il 12/09/2026 insieme alla sua chiamata in alert_checker.py.
def check_alerts(
    entries: list[dict] | None = None,
    states: dict | None = None,
    df_screening_global: pd.DataFrame | None = None,
) -> list[dict]:
    candidati: list[dict] = []

    # A. REVERSAL E LIVELLI (SOLO WATCHLIST)
    if entries and states:
        rows = []
        for e in entries:
            t = e["ticker"]
            s = states.get(t)
            if not s:
                continue
            rows.append({
                "Ticker": t,
                "Nome": s.get("nome", t),
                "Prezzo": s.get("price"),
                "DD%": s.get("dd", 0.0),
                "RSI": s.get("rsi", 50.0),
                "Segnale": s.get("segnale", "—"),
                "Wyckoff": s.get("wyckoff", "—"),
                "Sifrediana_Today": s.get("sifrediana_today", False),
                "Origine_Segnale": s.get("origine_segnale"),
                "SectorScore": s.get("sector_score"),
                "Vento": s.get("vento", "nd"),
                "Settore": s.get("settore", "—"),
                "Sotto-settore": s.get("sotto", "—"),
                "Bottom": s.get("bottom", "n/d"),
                "Link_TV": s.get("link_tv", ""),
            })
        if rows:
            candidati += compile_alerts(pd.DataFrame(rows))
        candidati += _level_alert_candidates(entries, states)
        candidati += _earnings_alert_candidates(entries, states)

    # B. CANDELONI GLOBALI (SCREENING, fuori watchlist)
    if df_screening_global is not None and not df_screening_global.empty:
        watchlist_tickers = {e["ticker"] for e in entries} if entries else set()
        global_df = df_screening_global[
            ~df_screening_global["Ticker"].isin(watchlist_tickers)
        ]
        if not global_df.empty:
            global_alerts = compile_alerts(global_df)
            candeloni_globali = [
                a for a in global_alerts if a["type"] == "SIFREDIANA"
            ]
            candidati += candeloni_globali

    # CONTROLLO DAY LOCK (5 GIORNI)
    state = _load_sent_alerts()
    oggi = _dt.date.today()
    alerts_to_send = []

    for a in candidati:
        t, kind = a["ticker"], a["type"]
        rec = state.get(f"{t}:{kind}")
        day_lock = False
        if rec:
            try:
                day_lock = (oggi - _dt.date.fromisoformat(rec["date"])).days < 5
            except Exception:
                day_lock = False
        if day_lock:
            continue
        alerts_to_send.append(a)

    # NON salviamo qui: salviamo SOLO dopo invio confermato in alert_checker.py
    return alerts_to_send


# ── Legacy UI ──
def process_and_send_alerts(df_screening: pd.DataFrame) -> list[str]:
    alerts = compile_alerts(df_screening)
    sent_tickers = []
    for a in alerts:
        if send_telegram_message(a["text"]):
            _register_sent_alert(
                a["ticker"], a["type"], price=a.get("price"), score=a.get("score")
            )
            sent_tickers.append(a["ticker"])
    return sent_tickers
