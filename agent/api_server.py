"""
api_server.py — Claude-style REST API Server na A23 5G

Telefon sam w sobie staje się API endpoint, który:
- Akceptuje requesty w formacie zbliżonym do Anthropic API
- Wzbogaca każde zapytanie o unified sensor context (fizyczna rzeczywistość)
- Odpowiada jak Claude, ale z "ciałem" i zmysłami

Endpointy:
  POST /v1/messages          — główny, kompatybilny z Anthropic SDK
  POST /v1/sms/send          — wyślij SMS
  GET  /v1/context           — aktualny snapshot sensorów
  POST /v1/action            — wykonaj akcję
  GET  /v1/health            — status agenta
  GET  /v1/photo             — zrób i zwróć zdjęcie
  WS   /v1/stream            — WebSocket stream zdarzeń
"""
import asyncio, json, logging, os, time
from datetime import datetime, timezone
from typing import Optional, Any

from fastapi import FastAPI, HTTPException, Depends, Header, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import sensor_fusion
from sensors import sms as sms_sensor, camera

log = logging.getLogger("api_server")

API_TOKEN = os.getenv("API_TOKEN", "")  # bearer token dla bezpieczeństwa
AGENT_NAME = os.getenv("AGENT_NAME", "Helios")


# ── Modele requestów ──────────────────────────────────────────────────────────

class MessageContent(BaseModel):
    type: str = "text"
    text: Optional[str] = None

class Message(BaseModel):
    role: str
    content: Any  # str lub list[MessageContent]

class MessagesRequest(BaseModel):
    model: Optional[str] = "helios-1"
    messages: list[Message]
    max_tokens: Optional[int] = 1024
    system: Optional[str] = None
    include_sensor_context: bool = True
    include_photo: bool = False
    stream: bool = False

class SMSSendRequest(BaseModel):
    to: str
    text: str

class ActionRequest(BaseModel):
    action: str
    params: dict = {}


# ── Auth ──────────────────────────────────────────────────────────────────────

def verify_token(authorization: Optional[str] = Header(None)):
    if not API_TOKEN:
        return  # brak tokenu = bez auth (tylko w sieci lokalnej!)
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.split(" ", 1)[1]
    if token != API_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")


# ── Factory ───────────────────────────────────────────────────────────────────

def create_app(l2_brain=None) -> FastAPI:
    app = FastAPI(
        title=f"{AGENT_NAME} API",
        description="Autonomous AI device API — A23 5G with full sensor context",
        version="1.0.0",
    )

    # ── POST /v1/messages — główny endpoint, Claude-kompatybilny ──────────────
    @app.post("/v1/messages")
    async def messages(req: MessagesRequest, _=Depends(verify_token)):
        start = time.time()

        # Zbierz kontekst sensorów (chyba że wyłączone)
        ctx = {}
        if req.include_sensor_context:
            ctx = await sensor_fusion.snapshot(include_photo=req.include_photo)

        # Wyodrębnij ostatnią wiadomość użytkownika
        user_messages = [m for m in req.messages if m.role == "user"]
        if not user_messages:
            raise HTTPException(status_code=400, detail="Brak wiadomości od użytkownika")
        last_user = user_messages[-1]
        text = last_user.content if isinstance(last_user.content, str) else \
               " ".join(c.get("text", "") for c in last_user.content if isinstance(c, dict))

        # Użyj Poziomu 2 (Claude API) jeśli dostępny
        if l2_brain:
            result = await l2_brain.query(text, ctx=ctx, include_photo=req.include_photo)
        else:
            # Fallback: odpowiedz z kontekstem bez Claude
            result = {
                "text": _local_response(text, ctx),
                "model": "helios-local-1",
                "tokens": 0,
                "context_summary": sensor_fusion.context_summary(ctx),
            }

        elapsed = round(time.time() - start, 3)

        # Odpowiedź w formacie kompatybilnym z Anthropic API
        return {
            "id": f"msg_{int(time.time() * 1000)}",
            "type": "message",
            "role": "assistant",
            "model": result.get("model", "helios-1"),
            "content": [{"type": "text", "text": result["text"]}],
            "stop_reason": "end_turn",
            "usage": {
                "input_tokens": len(text.split()),
                "output_tokens": result.get("tokens", 0),
            },
            "sensor_context": {
                "summary": result.get("context_summary", ""),
                "timestamp": ctx.get("timestamp"),
                "latency_s": elapsed,
            } if req.include_sensor_context else None,
        }

    # ── GET /v1/context — pełny snapshot sensorów ────────────────────────────
    @app.get("/v1/context")
    async def get_context(
        photo: bool = False,
        audio: bool = False,
        _=Depends(verify_token)
    ):
        ctx = await sensor_fusion.snapshot(include_photo=photo, include_audio=audio)
        # Usuń base64 z odpowiedzi (osobny endpoint /v1/photo)
        ctx_clean = {k: v for k, v in ctx.items() if k != "last_photo"}
        if photo and ctx.get("last_photo"):
            ctx_clean["last_photo"] = {
                "path": ctx["last_photo"]["path"],
                "size_kb": ctx["last_photo"]["size_kb"],
                "photo_url": "/v1/photo/latest",
            }
        return ctx_clean

    # ── GET /v1/photo — zrób zdjęcie i zwróć ─────────────────────────────────
    @app.get("/v1/photo")
    async def take_photo(cam: str = "back", _=Depends(verify_token)):
        from fastapi.responses import Response
        result = await asyncio.get_event_loop().run_in_executor(
            None, camera.capture, cam
        )
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        import base64
        img_bytes = base64.b64decode(result["base64"])
        return Response(content=img_bytes, media_type="image/jpeg")

    # ── POST /v1/sms/send ─────────────────────────────────────────────────────
    @app.post("/v1/sms/send")
    async def send_sms(req: SMSSendRequest, _=Depends(verify_token)):
        success = sms_sensor.send(req.to, req.text)
        return {"success": success, "to": req.to, "length": len(req.text)}

    # ── POST /v1/action ───────────────────────────────────────────────────────
    @app.post("/v1/action")
    async def run_action(req: ActionRequest, _=Depends(verify_token)):
        from brain import execute_action
        await execute_action({"action": req.action, **req.params})
        return {"executed": req.action}

    # ── GET /v1/health ────────────────────────────────────────────────────────
    @app.get("/v1/health")
    async def health():
        ctx = sensor_fusion.get_current()
        return {
            "status": "alive",
            "agent": AGENT_NAME,
            "uptime_s": int(time.time()),
            "battery": ctx.get("battery", {}),
            "connectivity": ctx.get("connectivity", {}),
            "context_age_s": (
                int(time.time() - datetime.fromisoformat(ctx["timestamp"]).timestamp())
                if ctx.get("timestamp") else None
            ),
            "api_version": "1.0.0",
        }

    # ── WS /v1/stream — real-time sensor stream ───────────────────────────────
    @app.websocket("/v1/stream")
    async def ws_stream(websocket: WebSocket):
        await websocket.accept()
        log.info("WebSocket client połączony")
        try:
            while True:
                ctx = await sensor_fusion.snapshot()
                ctx_clean = {k: v for k, v in ctx.items() if k != "last_photo"}
                await websocket.send_text(json.dumps(ctx_clean, default=str))
                await asyncio.sleep(int(os.getenv("SENSOR_INTERVAL_S", "10")))
        except WebSocketDisconnect:
            log.info("WebSocket client rozłączony")

    return app


# ── Lokalne odpowiedzi (bez Claude API) ──────────────────────────────────────

def _local_response(text: str, ctx: dict) -> str:
    """Prosta odpowiedź lokalna gdy brak klucza API"""
    t = text.lower()
    bat = ctx.get("battery", {})
    conn = ctx.get("connectivity", {})
    loc = ctx.get("location", {})
    summary = sensor_fusion.context_summary(ctx)

    if any(w in t for w in ["status", "co słychać", "jak się masz", "gdzie jesteś"]):
        return f"[{AGENT_NAME}] {summary}"

    if any(w in t for w in ["bateria", "battery", "ładowanie"]):
        return f"Bateria: {bat.get('level', '?')}% | Ładowanie: {'tak' if bat.get('charging') else 'nie'}"

    if any(w in t for w in ["lokalizacja", "gps", "gdzie"]):
        if loc.get("lat"):
            return f"Pozycja: {loc['lat']:.5f}, {loc['lon']:.5f} (dokładność {loc.get('accuracy_m', '?')}m)"
        return "GPS: brak sygnału"

    if any(w in t for w in ["sieć", "wifi", "internet"]):
        return f"Łączność: {conn.get('type', '?')} | IP: {conn.get('ip', '?')}"

    return f"[{AGENT_NAME}] OK. {summary}"
