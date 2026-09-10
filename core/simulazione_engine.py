"""
Motore di simulazione trading: crea e gestisce trade a partire dagli alert
REVERSAL con punteggio ≥ 4/6. Aggiorna PnL latente, verifica SL/TP, e chiude i trade.

Questo modulo viene eseguito dal workflow GitHub Actions dopo alert_checker.py.
Legge da: data/sent_alerts.json (generato da core/alerts.py)
Scrive su: data/simulazione_trades.csv (letto da pages/5_Simulazione.py)

LOGICA DI GESTIONE TRADE (Settembre 2026):
- SL: sull'ultimo minimo settimanale (ultime 4 settimane)
- TP1: RR 1:1,5 → chiude 20%, SL → breakeven
- TP2: +33% di gain → chiude 20%
- TP3: +50% di gain → chiude 30%
- TP4: +100% di gain → chiude 30%, trade chiuso

Scalata progressiva: 20% / 20% / 30% / 30% = 100%
"""
from __future__ import annotations

import json
import datetime as _dt
from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf

# ── Path (stessa convenzione del resto del progetto) ──────────
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SENT_ALERTS_FILE = DATA_DIR / "sent_alerts.json"
SIMULATION_CSV = DATA_DIR / "simulazione_trades.csv"
SIMULATION_LOG = DATA_DIR / "simulation_log.json"

# ── Parametri di gestione trade ───────────────────────────────
# Stop Loss: minimo delle ultime 4 settimane (28 giorni)
SL_LOOKBACK_DAYS = 28

# Take Profit targets (in ordine di esecuzione)
TP1_RR_RATIO = 1.5      # TP1 a RR 1:1,5
TP2_GAIN_PCT = 33.0     # TP2 a +33% di gain
TP3_GAIN_PCT = 50.0     # TP3 a +50% di gain
TP4_GAIN_PCT = 100.0    # TP4 a +100% di gain

# Scalata progressiva: percentuale di posizione chiusa ad ogni TP
TP1_CLOSE_PCT = 20.0    # TP1 chiude 20%
TP2_CLOSE_PCT = 20.0    # TP2 chiude 20%
TP3_CLOSE_PCT = 30.0    # TP3 chiude 30%
TP4_CLOSE_PCT = 30.0    # TP4 chiude 30% (totale = 100%)

# Score minimo per aprire un trade
MIN_SCORE_FOR_TRADE = 4


# ── I/O ───────────────────────────────────────────────────────
def load_sent_alerts() -> dict:
    """Carica lo stato degli alert inviati (generato da core/alerts.py)."""
    if not SENT_ALERTS_FILE.exists():
        return {}
    try:
        return json.loads(SENT_ALERTS_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"⚠️ Errore lettura sent_alerts.json: {e}")
        return {}


def load_simulation_trades() -> pd.DataFrame:
    """Carica i trade di simulazione dal CSV."""
    if not SIMULATION_CSV.exists():
        return _empty_trades_df()
    try:
        df = pd.read_csv(SIMULATION_CSV)
        if not df.empty:
            df['Data_Ingresso'] = pd.to_datetime(df['Data_Ingresso'])
            if 'Data_Uscita' in df.columns:
                df['Data_Uscita'] = pd.to_datetime(df['Data_Uscita'], errors='coerce')
        return df
    except Exception as e:
        print(f"⚠️ Errore caricamento CSV simulazione: {e}")
        return _empty_trades_df()


def _empty_trades_df() -> pd.DataFrame:
    """DataFrame vuoto con le colonne attese dalla pagina Streamlit."""
    return pd.DataFrame(columns=[
        'Ticker', 'Data_Ingresso', 'Prezzo_Ingresso',
        'SL_Prezzo', 'SL_Attuale',
        'TP1_Prezzo', 'TP2_Prezzo', 'TP3_Prezzo', 'TP4_Prezzo',
        'Quantita_Residua_%', 'PnL_Realizzato_%', 'PnL_Latente_%',
        'Max_Drawdown_%', 'Score_Alert', 'Stato',
        'Data_Uscita', 'Prezzo_Uscita', 'Motivo_Uscita', 'Note',
    ])


def save_simulation_trades(df: pd.DataFrame) -> None:
    """Salva i trade di simulazione nel CSV."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(SIMULATION_CSV, index=False)
        print(f"✅ Salvati {len(df)} trade in {SIMULATION_CSV}")
    except Exception as e:
        print(f"❌ Errore salvataggio CSV simulazione: {e}")


def save_log(entry: dict) -> None:
    """Salva un log dell'esecuzione per debug."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        log = []
        if SIMULATION_LOG.exists():
            log = json.loads(SIMULATION_LOG.read_text(encoding="utf-8"))
        log.append(entry)
        log = log[-50:]  # mantieni solo gli ultimi 50
        SIMULATION_LOG.write_text(
            json.dumps(log, indent=2, default=str, ensure_ascii=False),
            encoding="utf-8"
        )
    except Exception:
        pass


# ── Prezzi e minimi settimanali ──────────────────────────────
def get_current_price(ticker: str) -> Optional[float]:
    """Ottiene il prezzo corrente di un ticker via yfinance."""
    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period="5d")
        if hist.empty:
            return None
        return float(hist['Close'].iloc[-1])
    except Exception as e:
        print(f"⚠️ Errore prezzo per {ticker}: {e}")
        return None


def get_weekly_low(ticker: str, days: int = SL_LOOKBACK_DAYS) -> Optional[float]:
    """
    Ottiene il minimo delle ultime N settimane (default 4 settimane = 28 giorni).
    Usato per calcolare lo Stop Loss.
    """
    try:
        tk = yf.Ticker(ticker)
        # Scarica dati per il periodo necessario + buffer
        hist = tk.history(period=f"{days + 10}d")
        if hist.empty or len(hist) < 5:
            return None
        # Prendi gli ultimi N giorni
        recent = hist.tail(days)
        # Minimo dei prezzi Low
        weekly_low = float(recent['Low'].min())
        return weekly_low
    except Exception as e:
        print(f"⚠️ Errore calcolo minimo settimanale per {ticker}: {e}")
        return None


# ── Calcolo Take Profit ──────────────────────────────────────
def calculate_take_profits(entry_price: float, sl_price: float) -> dict:
    """
    Calcola i 4 Take Profit in base alla logica:
    - TP1: RR 1:1,5 (distanza SL × 1,5)
    - TP2: +33% di gain
    - TP3: +50% di gain
    - TP4: +100% di gain
    """
    # TP1: Risk-Reward 1:1,5
    distanza_sl = entry_price - sl_price
    tp1_price = entry_price + (distanza_sl * TP1_RR_RATIO)
    
    # TP2, TP3, TP4: percentuali di gain
    tp2_price = entry_price * (1 + TP2_GAIN_PCT / 100)
    tp3_price = entry_price * (1 + TP3_GAIN_PCT / 100)
    tp4_price = entry_price * (1 + TP4_GAIN_PCT / 100)
    
    return {
        'TP1_Prezzo': round(tp1_price, 4),
        'TP2_Prezzo': round(tp2_price, 4),
        'TP3_Prezzo': round(tp3_price, 4),
        'TP4_Prezzo': round(tp4_price, 4),
    }


# ── Logica principale ─────────────────────────────────────────
def find_new_trades_to_open(alerts_state: dict, existing_trades: pd.DataFrame) -> list[dict]:
    """
    Cerca nella history degli alert quelli REVERSAL con score ≥ MIN_SCORE_FOR_TRADE
    che non hanno già un trade aperto (o chiuso di recente) per lo stesso ticker.
    
    IMPORTANTE:
    - Apre trade SOLO per REVERSAL_GREEN e REVERSAL_YELLOW
    - NON apre trade per SIFREDIANA / CANDELONE (solo contesto informativo)
    """
    history = alerts_state.get("history", [])
    if not history:
        return []

    # Ticker che hanno già un trade APERTO → non riaprire
    open_tickers = set()
    if not existing_trades.empty:
        open_trades = existing_trades[existing_trades['Stato'] == 'Aperto']
        open_tickers = set(open_trades['Ticker'].unique())

    # Ticker che hanno già un trade CHIUSO negli ultimi 30 giorni → non riaprire
    recent_closed = set()
    if not existing_trades.empty:
        closed_trades = existing_trades[existing_trades['Stato'] == 'Chiuso'].copy()
        if not closed_trades.empty and 'Data_Uscita' in closed_trades.columns:
            cutoff = _dt.datetime.now() - _dt.timedelta(days=30)
            recent = closed_trades[pd.to_datetime(closed_trades['Data_Uscita'], errors='coerce') >= cutoff]
            recent_closed = set(recent['Ticker'].unique())

    # Filtra la history: solo REVERSAL con score sufficiente
    candidates = []
    for alert in history:
        kind = alert.get("kind", "")
        # ✅ APRIAMO SOLO per REVERSAL, NON per SIFREDIANA/CANDELONE
        if kind not in ("REVERSAL_GREEN", "REVERSAL_YELLOW"):
            continue
        score = alert.get("score")
        if score is None or score < MIN_SCORE_FOR_TRADE:
            continue
        candidates.append(alert)

    # Ordina per timestamp (i più recenti prima) e deduplica per ticker
    candidates.sort(key=lambda a: a.get("ts", ""), reverse=True)

    new_trades = []
    seen_tickers = set()
    for alert in candidates:
        ticker = alert["ticker"]
        if ticker in open_tickers or ticker in recent_closed or ticker in seen_tickers:
            continue
        seen_tickers.add(ticker)
        new_trades.append({
            "ticker": ticker,
            "alert_ts": alert["ts"],
            "alert_price": alert.get("price"),
            "score": alert["score"],
            "kind": alert["kind"],
        })

    return new_trades


def open_trade(ticker: str, entry_price: float, score: int,
               alert_ts: str, kind: str) -> Optional[dict]:
    """
    Crea un nuovo trade LONG con:
    - SL sull'ultimo minimo settimanale (ultime 4 settimane)
    - TP1 a RR 1:1,5
    - TP2 a +33%
    - TP3 a +50%
    - TP4 a +100%
    """
    # Calcola SL sul minimo settimanale
    sl_price = get_weekly_low(ticker, days=SL_LOOKBACK_DAYS)
    if sl_price is None:
        print(f"⚠️ Skip {ticker}: impossibile calcolare minimo settimanale")
        return None
    
    # Verifica che lo SL sia sotto il prezzo di ingresso (altrimenti non ha senso)
    if sl_price >= entry_price:
        print(f"⚠️ Skip {ticker}: SL ({sl_price:.2f}) >= Entry ({entry_price:.2f})")
        return None
    
    # Calcola i Take Profit
    take_profits = calculate_take_profits(entry_price, sl_price)
    
    return {
        "Ticker": ticker,
        "Data_Ingresso": _dt.datetime.fromisoformat(alert_ts.replace("Z", "")),
        "Prezzo_Ingresso": round(entry_price, 4),
        "SL_Prezzo": round(sl_price, 4),
        "SL_Attuale": round(sl_price, 4),
        **take_profits,
        "Quantita_Residua_%": 100.0,
        "PnL_Realizzato_%": 0.0,
        "PnL_Latente_%": 0.0,
        "Max_Drawdown_%": 0.0,
        "Score_Alert": score,
        "Stato": "Aperto",
        "Data_Uscita": None,
        "Prezzo_Uscita": None,
        "Motivo_Uscita": None,
        "Note": f"{kind} · {alert_ts[:10]} · SL={sl_price:.2f}",
    }


def update_open_trades(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggiorna tutti i trade aperti: calcola PnL latente, verifica SL/TP,
    e chiude parzialmente i trade ai Take Profit.
    
    LOGICA DI CHIUSURA:
    1. SL (-minimo settimanale): chiude il 100% della posizione
    2. TP1 (RR 1:1,5): chiude 20%, SL → breakeven
    3. TP2 (+33%): chiude 20%
    4. TP3 (+50%): chiude 30%
    5. TP4 (+100%): chiude 30%, trade chiuso
    """
    if df.empty:
        return df

    open_mask = df['Stato'] == 'Aperto'
    if not open_mask.any():
        return df

    print(f"🔄 Aggiornamento {open_mask.sum()} trade aperti...")

    for idx in df[open_mask].index:
        ticker = df.at[idx, 'Ticker']
        entry_price = df.at[idx, 'Prezzo_Ingresso']
        sl_price = df.at[idx, 'SL_Attuale']
        tp1_price = df.at[idx, 'TP1_Prezzo']
        tp2_price = df.at[idx, 'TP2_Prezzo']
        tp3_price = df.at[idx, 'TP3_Prezzo']
        tp4_price = df.at[idx, 'TP4_Prezzo']
        qty_pct = df.at[idx, 'Quantita_Residua_%']
        pnl_realizzato = df.at[idx, 'PnL_Realizzato_%']

        current_price = get_current_price(ticker)
        if current_price is None:
            print(f"⚠️ Skip {ticker}: prezzo non disponibile")
            continue

        # PnL latente sulla parte ancora aperta
        pnl_latente = ((current_price - entry_price) / entry_price) * 100
        df.at[idx, 'PnL_Latente_%'] = round(pnl_latente, 2)

        # Aggiorna max drawdown (considera sia realizzato che latente)
        pnl_totale = pnl_realizzato + (pnl_latente * qty_pct / 100)
        max_dd = df.at[idx, 'Max_Drawdown_%']
        if pnl_totale < max_dd:
            df.at[idx, 'Max_Drawdown_%'] = round(pnl_totale, 2)

        print(f"  • {ticker}: entry={entry_price:.2f}, current={current_price:.2f}, "
              f"PnL lat={pnl_latente:+.2f}%, qty={qty_pct:.0f}%")

        # ── Stop Loss ────────────────────────────────────────
        if current_price <= sl_price:
            df.at[idx, 'Stato'] = 'Chiuso'
            df.at[idx, 'Data_Uscita'] = _dt.datetime.now()
            df.at[idx, 'Prezzo_Uscita'] = round(current_price, 4)
            df.at[idx, 'PnL_Realizzato_%'] = round(
                pnl_realizzato + (pnl_latente * qty_pct / 100), 2
            )
            df.at[idx, 'PnL_Latente_%'] = 0.0
            df.at[idx, 'Quantita_Residua_%'] = 0.0
            df.at[idx, 'Motivo_Uscita'] = 'Stop Loss'
            print(f"    ❌ SL @ {current_price:.2f}")
            continue

        # ── TP4 (+100%): chiude 30% restante, trade chiuso ───
        if current_price >= tp4_price and qty_pct > 0:
            closed_qty = min(qty_pct, TP4_CLOSE_PCT)
            df.at[idx, 'PnL_Realizzato_%'] = round(
                pnl_realizzato + (pnl_latente * closed_qty / 100), 2
            )
            df.at[idx, 'Quantita_Residua_%'] = 0.0
            df.at[idx, 'Stato'] = 'Chiuso'
            df.at[idx, 'Data_Uscita'] = _dt.datetime.now()
            df.at[idx, 'Prezzo_Uscita'] = round(current_price, 4)
            df.at[idx, 'PnL_Latente_%'] = 0.0
            df.at[idx, 'Motivo_Uscita'] = 'Take Profit 4 (+100%)'
            df.at[idx, 'Note'] = df.at[idx, 'Note'] + ' | TP4 raggiunto'
            print(f"    ✅ TP4 @ {current_price:.2f}: chiuso {closed_qty:.0f}%, trade completato")
            continue

        # ── TP3 (+50%): chiude 30% ───────────────────────────
        # Controlla se TP3 è già stato raggiunto (qty < 60% significa che TP1 e TP2 sono stati raggiunti)
        tp3_already_reached = qty_pct <= 30.01  # Dopo TP1+TP2 resta 60%, dopo TP3 resta 30%
        
        if current_price >= tp3_price and not tp3_already_reached and qty_pct > 30:
            closed_qty = TP3_CLOSE_PCT
            df.at[idx, 'PnL_Realizzato_%'] = round(
                pnl_realizzato + (pnl_latente * closed_qty / 100), 2
            )
            df.at[idx, 'Quantita_Residua_%'] = qty_pct - closed_qty
            df.at[idx, 'Note'] = df.at[idx, 'Note'] + f' | TP3 raggiunto @ {current_price:.2f}'
            print(f"    🎯 TP3 @ {current_price:.2f}: chiuso {closed_qty:.0f}%, qty residua={qty_pct - closed_qty:.0f}%")
            # Non fare continue: il trade resta aperto con il restante 30%

        # ── TP2 (+33%): chiude 20% ───────────────────────────
        # Controlla se TP2 è già stato raggiunto (qty < 80% significa che TP1 è stato raggiunto)
        tp2_already_reached = qty_pct <= 60.01  # Dopo TP1 resta 80%, dopo TP2 resta 60%
        
        if current_price >= tp2_price and not tp2_already_reached and qty_pct > 60:
            closed_qty = TP2_CLOSE_PCT
            df.at[idx, 'PnL_Realizzato_%'] = round(
                pnl_realizzato + (pnl_latente * closed_qty / 100), 2
            )
            df.at[idx, 'Quantita_Residua_%'] = qty_pct - closed_qty
            df.at[idx, 'Note'] = df.at[idx, 'Note'] + f' | TP2 raggiunto @ {current_price:.2f}'
            print(f"    🎯 TP2 @ {current_price:.2f}: chiuso {closed_qty:.0f}%, qty residua={qty_pct - closed_qty:.0f}%")
            # Non fare continue: il trade resta aperto con il restante 60%

        # ── TP1 (RR 1:1,5): chiude 20%, SL → breakeven ──────
        # Controlla se TP1 è già stato raggiunto (SL già spostato a breakeven)
        tp1_already_reached = (round(df.at[idx, 'SL_Attuale'], 4) ==
                               round(df.at[idx, 'Prezzo_Ingresso'], 4) and
                               qty_pct < 100)
        
        if current_price >= tp1_price and not tp1_already_reached and qty_pct == 100:
            closed_qty = TP1_CLOSE_PCT
            df.at[idx, 'PnL_Realizzato_%'] = round(
                pnl_realizzato + (pnl_latente * closed_qty / 100), 2
            )
            df.at[idx, 'Quantita_Residua_%'] = qty_pct - closed_qty
            # Trailing stop: sposta SL a breakeven
            df.at[idx, 'SL_Attuale'] = round(entry_price, 4)
            df.at[idx, 'Note'] = df.at[idx, 'Note'] + f' | TP1 raggiunto @ {current_price:.2f}, SL → breakeven'
            print(f"    🎯 TP1 @ {current_price:.2f}: chiuso {closed_qty:.0f}%, SL → breakeven")
            # Non fare continue: il trade resta aperto con il restante 80%

    return df


# ── Entry point ───────────────────────────────────────────────
def run_simulation() -> tuple[int, int]:
    """
    Esegue il simulatore: apre nuovi trade e aggiorna quelli esistenti.
    Ritorna (nuovi_trade_aperti, trade_chiusi).
    """
    print("=" * 60)
    print("🎮 AVVIO SIMULATORE DI TRADING")
    print("=" * 60)

    # Carica stato alert
    alerts_state = load_sent_alerts()
    if not alerts_state:
        print("⚠️ Nessun alert trovato in sent_alerts.json")
        save_log({"ts": _dt.datetime.now().isoformat(),
                  "status": "no_alerts", "new": 0, "closed": 0})
        return 0, 0

    history = alerts_state.get("history", [])
    print(f"📋 Alert totali in history: {len(history)}")

    # Carica trade esistenti
    df = load_simulation_trades()
    print(f"📊 Trade esistenti: {len(df)}")

    # Trova nuovi trade da aprire
    new_trades_info = find_new_trades_to_open(alerts_state, df)
    print(f"\n🔍 Candidati per nuovi trade: {len(new_trades_info)}")

    new_trades = []
    for info in new_trades_info:
        ticker = info["ticker"]
        entry_price = info.get("alert_price")
        if entry_price is None:
            entry_price = get_current_price(ticker)
        if entry_price is None:
            print(f"⚠️ Skip {ticker}: prezzo non disponibile")
            continue

        trade = open_trade(
            ticker=ticker,
            entry_price=entry_price,
            score=info["score"],
            alert_ts=info["alert_ts"],
            kind=info["kind"],
        )
        if trade:
            new_trades.append(trade)
            print(f"✅ Nuovo trade: {ticker} @ {entry_price:.2f} "
                  f"(score {info['score']}/6, {info['kind']})")
            print(f"   SL={trade['SL_Prezzo']:.2f}, TP1={trade['TP1_Prezzo']:.2f}, "
                  f"TP2={trade['TP2_Prezzo']:.2f}, TP3={trade['TP3_Prezzo']:.2f}, "
                  f"TP4={trade['TP4_Prezzo']:.2f}")

    # Aggiungi nuovi trade al DataFrame
    if new_trades:
        new_df = pd.DataFrame(new_trades)
        df = pd.concat([df, new_df], ignore_index=True)

    # Conta trade aperti prima dell'aggiornamento
    trades_before = len(df[df['Stato'] == 'Aperto']) if not df.empty else 0

    # Aggiorna trade aperti (PnL, SL, TP)
    df = update_open_trades(df)

    trades_after = len(df[df['Stato'] == 'Aperto']) if not df.empty else 0
    closed_trades = trades_before - trades_after

    # Salva
    save_simulation_trades(df)

    # Log
    save_log({
        "ts": _dt.datetime.now().isoformat(),
        "status": "ok",
        "new": len(new_trades),
        "closed": closed_trades,
        "open_remaining": trades_after,
    })

    print("\n" + "=" * 60)
    print(f"📊 RIEPILOGO:")
    print(f"   • Nuovi trade aperti: {len(new_trades)}")
    print(f"   • Trade chiusi in questa esecuzione: {closed_trades}")
    print(f"   • Trade ancora aperti: {trades_after}")
    print("=" * 60)

    return len(new_trades), closed_trades


if __name__ == "__main__":
    run_simulation()
