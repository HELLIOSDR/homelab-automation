"""Camera sensor — zdjęcia przez Termux:API"""
import subprocess, base64, os, time
from typing import Optional
from pathlib import Path

PHOTO_DIR = Path.home() / "ai_agent/data/photos"
PHOTO_DIR.mkdir(parents=True, exist_ok=True)

def capture(camera: str = "back", quality: int = 80) -> dict:
    """Zrób zdjęcie, zwróć ścieżkę i base64 (dla Claude Vision)"""
    ts = int(time.time())
    path = PHOTO_DIR / f"capture_{ts}.jpg"
    try:
        result = subprocess.run(
            ["termux-camera-photo", "-c", "0" if camera == "back" else "1", str(path)],
            capture_output=True, timeout=20
        )
        if path.exists():
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            return {
                "path": str(path),
                "base64": b64,
                "size_kb": path.stat().st_size // 1024,
                "timestamp": ts,
                "camera": camera
            }
        return {"error": "Zdjęcie nie zostało zapisane", "stderr": result.stderr.decode()}
    except Exception as e:
        return {"error": str(e)}

def latest_photo() -> Optional[dict]:
    """Ostatnie zdjęcie jako base64"""
    photos = sorted(PHOTO_DIR.glob("*.jpg"), key=os.path.getmtime, reverse=True)
    if not photos:
        return None
    p = photos[0]
    with open(p, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return {"path": str(p), "base64": b64, "age_s": int(time.time() - p.stat().st_mtime)}
