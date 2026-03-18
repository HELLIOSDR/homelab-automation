"""GPS sensor — lokalizacja przez Termux:API"""
import subprocess, json, time, math
from typing import Optional

_last: dict = {}

def read() -> dict:
    global _last
    try:
        out = subprocess.run(
            ["termux-location", "-p", "gps", "-r", "once"],
            capture_output=True, text=True, timeout=15
        ).stdout.strip()
        data = json.loads(out) if out else {}
        if data:
            data["moving"] = _is_moving(data)
            _last = data
        return data
    except Exception as e:
        return {**_last, "stale": True, "error": str(e)} if _last else {}

def _is_moving(new: dict) -> bool:
    if not _last or "latitude" not in _last:
        return False
    # >10m od ostatniej pozycji = ruch
    try:
        dist = _haversine(
            _last["latitude"], _last["longitude"],
            new["latitude"], new["longitude"]
        )
        return dist > 10
    except Exception:
        return False

def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))
