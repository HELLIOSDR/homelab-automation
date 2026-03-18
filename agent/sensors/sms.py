"""SMS sensor + sender — przez Termux:API"""
import subprocess, json, time
from typing import Optional

_seen_ids: set = set()

def read_pending() -> list[dict]:
    """Zwraca nowe SMS (jeszcze nie przetworzone)"""
    try:
        out = subprocess.run(
            ["termux-sms-list", "-l", "20", "-t", "inbox"],
            capture_output=True, text=True, timeout=10
        ).stdout.strip()
        messages = json.loads(out) if out else []
        new = [m for m in messages if m.get("_id") not in _seen_ids]
        for m in new:
            _seen_ids.add(m.get("_id"))
        return new
    except Exception:
        return []

def send(number: str, text: str) -> bool:
    """Wyślij SMS na numer"""
    try:
        # Podziel na kawałki max 160 znaków jeśli długi
        chunks = [text[i:i+155] for i in range(0, len(text), 155)]
        for i, chunk in enumerate(chunks):
            msg = chunk if len(chunks) == 1 else f"[{i+1}/{len(chunks)}] {chunk}"
            subprocess.run(
                ["termux-sms-send", "-n", number, msg],
                capture_output=True, timeout=30
            )
        return True
    except Exception:
        return False

def get_sim_info() -> dict:
    """Informacje o karcie SIM i sygnale"""
    try:
        out = subprocess.run(
            ["termux-telephony-deviceinfo"],
            capture_output=True, text=True, timeout=10
        ).stdout.strip()
        return json.loads(out) if out else {}
    except Exception:
        return {}
