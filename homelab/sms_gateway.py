"""
sms_gateway.py — Homelab-side bridge do A23 5G

Uruchamia się na serwerze homelab.
Utrzymuje połączenie SSH z telefonem i eksponuje:
  - REST API do wysyłania SMS-ów przez telefon
  - Webhook dla przychodzących SMS-ów
  - Monitoring stanu telefonu

Użycie:
  python homelab/sms_gateway.py

Wymagania: pip install fastapi uvicorn paramiko aiohttp python-dotenv
"""
import asyncio, json, logging, os, time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

import aiohttp
import uvicorn
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel

PHONE_API_URL  = os.getenv("PHONE_API_URL", "http://localhost:7788")
PHONE_API_TOKEN = os.getenv("PHONE_API_TOKEN", "")
GATEWAY_PORT   = int(os.getenv("GATEWAY_PORT", "8080"))
AGENT_NAME     = os.getenv("AGENT_NAME", "Helios")

log = logging.getLogger("sms_gateway")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [gateway] %(levelname)s — %(message)s")

app = FastAPI(title="Homelab SMS Gateway", description=f"Bridge to {AGENT_NAME} on A23 5G")

_phone_headers = {"Authorization": f"Bearer {PHONE_API_TOKEN}"} if PHONE_API_TOKEN else {}


# ── Models ────────────────────────────────────────────────────────────────────

class SendSMSRequest(BaseModel):
    to: str
    text: str

class QueryRequest(BaseModel):
    prompt: str
    include_photo: bool = False
    include_sensor_context: bool = True

class WebhookSMSEvent(BaseModel):
    from_number: str
    text: str
    timestamp: str = ""


# ── Helpers ───────────────────────────────────────────────────────────────────

async def phone_get(path: str, **kwargs) -> dict:
    async with aiohttp.ClientSession() as s:
        r = await s.get(f"{PHONE_API_URL}{path}", headers=_phone_headers,
                        timeout=aiohttp.ClientTimeout(total=15), **kwargs)
        return await r.json()

async def phone_post(path: str, data: dict, **kwargs) -> dict:
    async with aiohttp.ClientSession() as s:
        r = await s.post(f"{PHONE_API_URL}{path}", json=data, headers=_phone_headers,
                         timeout=aiohttp.ClientTimeout(total=30), **kwargs)
        return await r.json()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Status gateway i telefonu"""
    phone_status = {}
    phone_ok = False
    try:
        phone_status = await phone_get("/v1/health")
        phone_ok = phone_status.get("status") == "alive"
    except Exception as e:
        phone_status = {"error": str(e)}

    return {
        "gateway": "alive",
        "phone_reachable": phone_ok,
        "phone": phone_status,
        "phone_api": PHONE_API_URL,
        "timestamp": datetime.utcnow().isoformat(),
    }

@app.post("/sms/send")
async def send_sms(req: SendSMSRequest):
    """Wyślij SMS przez telefon"""
    try:
        result = await phone_post("/v1/sms/send", {"to": req.to, "text": req.text})
        return result
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Nie można połączyć z telefonem: {e}")

@app.post("/query")
async def query(req: QueryRequest):
    """Wyślij zapytanie do AI na telefonie z kontekstem sensorów"""
    try:
        payload = {
            "model": "helios-1",
            "messages": [{"role": "user", "content": req.prompt}],
            "include_sensor_context": req.include_sensor_context,
            "include_photo": req.include_photo,
        }
        result = await phone_post("/v1/messages", payload)
        return result
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

@app.get("/context")
async def get_context(photo: bool = False):
    """Aktualny sensor snapshot z telefonu"""
    try:
        return await phone_get(f"/v1/context?photo={photo}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

@app.get("/photo")
async def get_photo():
    """Zdjęcie z tylnej kamery telefonu"""
    from fastapi.responses import StreamingResponse
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(f"{PHONE_API_URL}/v1/photo", headers=_phone_headers,
                            timeout=aiohttp.ClientTimeout(total=25))
            return StreamingResponse(r.content, media_type="image/jpeg")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

@app.post("/webhook/sms")
async def sms_webhook(event: WebhookSMSEvent):
    """Homelab może rejestrować tu przychodzące SMS-y (forwarded z telefonu)"""
    log.info(f"SMS webhook: {event.from_number} → '{event.text[:80]}'")
    # Tutaj możesz integrować z innymi systemami homelab (np. Home Assistant, MQTT)
    return {"received": True}

@app.post("/alert/{severity}")
async def receive_alert(severity: str, body: dict):
    """Alerty z telefonu (bateria, ruch, etc.)"""
    log.warning(f"ALERT [{severity.upper()}] from {AGENT_NAME}: {body.get('message', body)}")
    # Możesz tu dodać: MQTT publish, ntfy.sh push, email, itp.
    return {"acknowledged": True}


# ── Monitor loop ──────────────────────────────────────────────────────────────

async def monitor_phone():
    """Sprawdza co 60s czy telefon żyje"""
    while True:
        await asyncio.sleep(60)
        try:
            status = await phone_get("/v1/health")
            bat = status.get("battery", {}).get("level", "?")
            log.info(f"Telefon: OK | bateria {bat}%")
        except Exception:
            log.warning(f"Telefon: NIEDOSTĘPNY ({PHONE_API_URL})")


if __name__ == "__main__":
    async def run():
        asyncio.create_task(monitor_phone())
        config = uvicorn.Config(app, host="0.0.0.0", port=GATEWAY_PORT, log_level="info")
        await uvicorn.Server(config).serve()

    asyncio.run(run())
