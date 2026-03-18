"""Audio sensor — wykrywanie głosu/dźwięku przez Termux:API"""
import subprocess, json, os, time, threading
from pathlib import Path

AUDIO_DIR = Path.home() / "ai_agent/data/audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

def measure_ambient_db(duration_ms: int = 500) -> float:
    """Zmierz głośność otoczenia (dB)"""
    try:
        out = subprocess.run(
            ["termux-microphone-record", "-l", str(duration_ms // 1000 or 1),
             "-f", str(AUDIO_DIR / "ambient_sample.mp4")],
            capture_output=True, timeout=duration_ms // 1000 + 5
        )
        # Jeśli nie ma narzędzia do pomiaru dB, zwróć -1 (nieznane)
        return -1.0
    except Exception:
        return -1.0

def detect_voice(duration_s: int = 3) -> dict:
    """Nagraj krótki fragment i wykryj obecność głosu"""
    path = AUDIO_DIR / f"voice_{int(time.time())}.mp4"
    try:
        subprocess.run(
            ["termux-microphone-record", "-l", str(duration_s), "-f", str(path)],
            capture_output=True, timeout=duration_s + 10
        )
        voice_detected = path.exists() and path.stat().st_size > 10000
        return {
            "voice_detected": voice_detected,
            "file": str(path) if voice_detected else None,
            "duration_s": duration_s
        }
    except Exception as e:
        return {"voice_detected": False, "error": str(e)}

def transcribe(audio_path: str, api_key: str) -> str:
    """Transkrypcja przez Whisper API (jeśli skonfigurowane)"""
    try:
        import requests
        with open(audio_path, "rb") as f:
            r = requests.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (os.path.basename(audio_path), f, "audio/mp4")},
                data={"model": "whisper-1"},
                timeout=30
            )
        return r.json().get("text", "") if r.ok else ""
    except Exception:
        return ""
