"""
sensor_fusion.py — Unified Sensor Context
Zbiera wszystkie zmysły w jeden obiekt, który trafia do Claude jako świadomość urządzenia.
"""
import asyncio, time, logging
from datetime import datetime, timezone
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

from sensors import gps, sms, camera, motion, audio, system

log = logging.getLogger("sensor_fusion")

_executor = ThreadPoolExecutor(max_workers=6, thread_name_prefix="sensor")

# Ostatni znany kontekst — zawsze dostępny nawet przy błędach sensorów
_current_context: dict = {}

async def _run_sensor(fn, *args, timeout: float = 5.0) -> Optional[dict]:
    """Uruchamia sensor asynchronicznie z timeoutem"""
    loop = asyncio.get_event_loop()
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(_executor, fn, *args),
            timeout=timeout
        )
        return result
    except (asyncio.TimeoutError, FutureTimeout):
        log.debug(f"Sensor timeout: {fn.__module__}.{fn.__name__}")
        return None
    except Exception as e:
        log.debug(f"Sensor error {fn.__module__}: {e}")
        return None

async def snapshot(
    include_photo: bool = False,
    include_audio: bool = False,
) -> dict:
    """
    Zbiera pełny kontekst urządzenia asynchronicznie.
    Każdy sensor ma swój timeout — jeden padający nie blokuje reszty.
    """
    ts = time.time()

    # Uruchom wszystkie sensory równolegle
    tasks = {
        "location": _run_sensor(gps.read, timeout=15),
        "motion":   _run_sensor(motion.read, timeout=5),
        "system":   _run_sensor(system.read, timeout=8),
        "sms":      _run_sensor(sms.read_pending, timeout=10),
        "sim":      _run_sensor(sms.get_sim_info, timeout=5),
    }

    if include_photo:
        tasks["photo"] = _run_sensor(camera.capture, timeout=20)

    if include_audio:
        tasks["audio_sample"] = _run_sensor(audio.detect_voice, 2, timeout=15)

    results = dict(zip(tasks.keys(), await asyncio.gather(*tasks.values())))

    # Złóż unified context
    loc = results.get("location") or {}
    mot = results.get("motion") or {}
    sys_data = results.get("system") or {}
    bat = sys_data.get("battery", {})
    conn = sys_data.get("connectivity", {})

    ctx = {
        "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
        "device": "A23_5G",

        "location": {
            "lat": loc.get("latitude"),
            "lon": loc.get("longitude"),
            "accuracy_m": loc.get("accuracy"),
            "altitude_m": loc.get("altitude"),
            "moving": loc.get("moving", False),
            "stale": loc.get("stale", False),
        },

        "motion": {
            "shake": mot.get("accelerometer", {}).get("shake", False),
            "moving": mot.get("accelerometer", {}).get("moving", False),
            "magnitude": mot.get("accelerometer", {}).get("magnitude"),
            "steps": mot.get("steps"),
        },

        "battery": {
            "level": bat.get("percentage", bat.get("level")),
            "status": bat.get("status", "unknown"),
            "charging": bat.get("plugged", "unplugged") != "unplugged",
        },

        "connectivity": {
            "type": conn.get("type", "unknown"),
            "ssid": conn.get("ssid"),
            "signal": conn.get("signal_strength"),
            "ip": conn.get("ip"),
        },

        "system": {
            "memory_available_mb": sys_data.get("memory", {}).get("available_mb"),
            "cpu_percent": sys_data.get("cpu_percent"),
            "temperature_c": sys_data.get("temperature_c"),
        },

        "pending_sms": results.get("sms") or [],
        "sms_count_pending": len(results.get("sms") or []),

        "sim": results.get("sim") or {},
    }

    if include_photo and results.get("photo"):
        p = results["photo"]
        ctx["last_photo"] = {
            "path": p.get("path"),
            "base64": p.get("base64"),  # dla Claude Vision
            "size_kb": p.get("size_kb"),
        }

    if include_audio and results.get("audio_sample"):
        ctx["audio"] = results["audio_sample"]

    # Zaktualizuj globalny kontekst
    global _current_context
    _current_context = ctx

    return ctx

def get_current() -> dict:
    """Zwraca ostatni znany kontekst bez nowego odczytu sensorów"""
    return _current_context

def context_summary(ctx: dict) -> str:
    """Zwraca krótki tekstowy opis kontekstu dla logów i powiadomień"""
    bat = ctx.get("battery", {})
    conn = ctx.get("connectivity", {})
    loc = ctx.get("location", {})
    parts = []

    if bat.get("level") is not None:
        chg = "⚡" if bat.get("charging") else "🔋"
        parts.append(f"{chg}{bat['level']}%")

    if conn.get("type"):
        parts.append(conn["type"])

    if loc.get("lat") and loc.get("lon"):
        parts.append(f"GPS({loc['lat']:.4f},{loc['lon']:.4f})")
    elif loc.get("stale"):
        parts.append("GPS(stale)")

    if ctx.get("motion", {}).get("shake"):
        parts.append("SHAKE!")

    if ctx.get("sms_count_pending", 0) > 0:
        parts.append(f"{ctx['sms_count_pending']} SMS")

    return " | ".join(parts) if parts else "no data"
