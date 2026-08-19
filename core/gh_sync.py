"""
Write-through dei file di stato su GitHub (solo su Streamlit Cloud, dove
esistono GITHUB_TOKEN e GITHUB_REPO). In locale è no-op.
Rende persistenti watchlist/alerts tra i redeploy.
"""
from __future__ import annotations
import base64
import os
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent

def _secret(name: str) -> str | None:
    v = os.environ.get(name)
    if v:
        return v
    try:
        import streamlit as st
        try:
            return st.secrets[name]
        except Exception:
            return None
    except Exception:
        return None

def publish_file(rel_path: str, message: str, branch: str = "main") -> bool:
    token = _secret("GITHUB_TOKEN")
    repo = _secret("GITHUB_REPO")
    if not token or not repo:
        return False
    local = ROOT / rel_path
    if not local.exists():
        return False
    headers = {"Authorization": f"token {token}",
               "Accept": "application/vnd.github+json"}
    api = f"https://api.github.com/repos/{repo}/contents/{rel_path}"
    try:
        r = requests.get(api, headers=headers, timeout=15)
        sha = r.json().get("sha") if r.ok else None
        payload = {"message": message,
                   "content": base64.b64encode(local.read_bytes()).decode(),
                   "branch": branch}
        if sha:
            payload["sha"] = sha
        r2 = requests.put(api, headers=headers, json=payload, timeout=30)
        return bool(r2.ok)
    except Exception:
        return False

def publish_watchlist() -> bool:
    return publish_file("data/watchlist.json",
                        "chore(portale): aggiorna watchlist")
