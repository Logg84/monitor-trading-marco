"""
Screening in thread background: la navigazione tra pagine NON lo interrompe.
Il risultato è scritto anche nella cache su disco (save_screening_cache).
"""
from __future__ import annotations
import datetime as _dt
import threading
from core.data_engine import screening, save_screening_cache

_STATE = {
    "running": False, "done": False, "df": None, "diag": None,
    "log": [], "started_at": None, "index_label": None,
    "per_index": None, "gross": None,
}
_LOCK = threading.Lock()

def start(tickers: list, per_index: dict, gross: int, index_label: str) -> bool:
    with _LOCK:
        if _STATE["running"]:
            return False
        _STATE.update(running=True, done=False, df=None, diag=None, log=[],
                      started_at=_dt.datetime.now().isoformat(timespec="seconds"),
                      index_label=index_label, per_index=per_index, gross=gross)

    def worker():
        try:
            df, diag = screening(tickers, log=lambda m: _STATE["log"].append(m))
            if diag.get("valid", 0) > 0:
                save_screening_cache(df, {"index": index_label,
                                          "diagnostics": diag,
                                          "per_index": per_index,
                                          "gross": gross})
            with _LOCK:
                _STATE["df"] = df
                _STATE["diag"] = diag
                _STATE["done"] = True
        except Exception as e:
            with _LOCK:
                _STATE["log"].append(f"Errore: {e}")
                _STATE["done"] = True
        finally:
            with _LOCK:
                _STATE["running"] = False

    threading.Thread(target=worker, daemon=True).start()
    return True

def snapshot() -> dict:
    with _LOCK:
        return {"running": _STATE["running"], "done": _STATE["done"],
                "df": _STATE["df"], "diag": _STATE["diag"],
                "log": list(_STATE["log"]), "started_at": _STATE["started_at"],
                "index_label": _STATE["index_label"],
                "per_index": _STATE["per_index"], "gross": _STATE["gross"]}
