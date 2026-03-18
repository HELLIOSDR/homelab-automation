"""
brain.py — Dwupoziomowy mózg AI dla A23 5G

POZIOM 1 (Fast/Local): event loop, reguły lokalne, natychmiastowe reakcje
POZIOM 2 (Claude API): pełne rozumowanie z unified sensor context

Uruchamia się automatycznie przez Termux:Boot lub ręcznie: python brain.py
"""
import asyncio, json, logging, os, time, signal, sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path.home() / "ai_agent/.env")

import anthropic
import sensor_fusion
from sensors import sms as sms_sensor

# ── Konfiguracja ──────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
ALLOWED_NUMBERS    = set(os.getenv("ALLOWED_NUMBERS", "").split(","))
HOMELAB_WEBHOOK    = os.getenv("HOMELAB_WEBHOOK_URL", "")
AGENT_NAME         = os.getenv("AGENT_NAME", "Helios")
SENSOR_INTERVAL    = int(os.getenv("SENSOR_INTERVAL_S", "10"))
API_PORT           = int(os.getenv("API_PORT", "7788"))
LOG_DIR            = Path.home() / "ai_agent/logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "agent.log"),
    ]
)
log = logging.getLogger("brain")

claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

# ── Persona ───────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = f"""Jesteś {AGENT_NAME} — autonomicznym AI agentem zainstalowanym na fizycznym urządzeniu mobilnym.
Masz dostęp do sensorów: GPS, kamera, mikrofon, akcelerometr, SMS/SIM.
Urządzenie jest zawsze przy Tobie — masz wbudowaną świadomość fizyczną.

Zawsze otrzymujesz unified_context — snapshot wszystkich zmysłów w danej chwili.
Odpowiadaj konkretnie, z uwzględnieniem fizycznej rzeczywistości urządzenia.
Jeśli ktoś pyta gdzie jesteś — używasz GPS. Jeśli co widzisz — robisz zdjęcie.
Odpowiedzi przez SMS muszą być zwięzłe (max 160 znaków per kawałek).
Możesz wydawać komendy: {{"action": "send_sms", "to": "numer", "text": "treść"}}
                        {{"action": "take_photo", "camera": "back"}}
                        {{"action": "alert_homelab", "message": "tekst"}}
                        {{"action": "shell", "command": "cmd"}}"""

# ── Poziom 1: Reguły lokalne ──────────────────────────────────────────────────

class Level1Engine:
    """Natychmiastowe reakcje bez API call"""

    def __init__(self, l2: "Level2Brain"):
        self.l2 = l2
        self._last_bat_alert = 0

    async def process(self, ctx: dict) -> list[dict]:
        """Zwraca listę akcji do wykonania"""
        actions = []

        # Alert niski poziom baterii
        bat = ctx.get("battery", {})
        if bat.get("level") and bat["level"] < 15 and not bat.get("charging"):
            if time.time() - self._last_bat_alert > 3600:
                self._last_bat_alert = time.time()
                actions.append({
                    "action": "alert_homelab",
                    "message": f"⚠️ {AGENT_NAME}: Bateria {bat['level']}% — ładuj teraz!"
                })

        # SMS od autoryzowanego numeru → Poziom 2
        for msg in ctx.get("pending_sms", []):
            sender = msg.get("number", "")
            text = msg.get("body", "").strip()
            if _is_authorized(sender):
                log.info(f"SMS od {sender}: {text[:50]}")
                # Eskaluj do Poziomu 2
                asyncio.create_task(self.l2.handle_sms(ctx, sender, text))
            else:
                log.debug(f"SMS od nieautoryzowanego {sender} — ignoruję")

        # Silne wstrząsy → log i alert
        if ctx.get("motion", {}).get("shake"):
            log.warning("Wykryto wstrząs urządzenia!")
            actions.append({
                "action": "alert_homelab",
                "message": f"⚡ {AGENT_NAME}: Wykryto silny wstrząs!"
            })

        return actions


# ── Poziom 2: Claude API ──────────────────────────────────────────────────────

class Level2Brain:
    """Pełne rozumowanie z Claude API"""

    async def handle_sms(self, ctx: dict, sender: str, text: str):
        """Odpowiedz na SMS z pełnym kontekstem rzeczywistości"""
        if not claude:
            sms_sensor.send(sender, f"[{AGENT_NAME}] Brak klucza API — skonfiguruj ANTHROPIC_API_KEY")
            return

        log.info(f"Poziom 2: przetwarzam SMS od {sender}")

        # Zbuduj prompt z kontekstem fizycznym
        ctx_str = json.dumps(ctx, ensure_ascii=False, default=str)
        user_msg = f"""Kontekst urządzenia (teraz):
{ctx_str}

Wiadomość SMS od {sender}:
"{text}"

Odpowiedz krótko (SMS, max 2-3 zdania). Jeśli potrzebujesz akcji, zwróć JSON z polem "action"."""

        try:
            response = claude.messages.create(
                model="claude-opus-4-6",
                max_tokens=500,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}]
            )
            reply_text = response.content[0].text

            # Sprawdź czy odpowiedź zawiera JSON z akcją
            try:
                if "{" in reply_text and "action" in reply_text:
                    start = reply_text.find("{")
                    end = reply_text.rfind("}") + 1
                    action = json.loads(reply_text[start:end])
                    await execute_action(action)
                    # Wyślij tylko tekstową część
                    clean_reply = reply_text[:start].strip()
                    if clean_reply:
                        sms_sensor.send(sender, clean_reply)
                else:
                    sms_sensor.send(sender, reply_text)
            except json.JSONDecodeError:
                sms_sensor.send(sender, reply_text)

            log.info(f"Odpowiedziałem {sender}: {reply_text[:80]}...")

        except Exception as e:
            log.error(f"Claude API error: {e}")
            sms_sensor.send(sender, f"[{AGENT_NAME}] Błąd przetwarzania: {str(e)[:100]}")

    async def query(self, prompt: str, ctx: dict = None, include_photo: bool = False) -> dict:
        """Ogólny query do Claude z opcjonalnym kontekstem sensorów"""
        if not claude:
            return {"error": "Brak ANTHROPIC_API_KEY"}

        if ctx is None:
            ctx = await sensor_fusion.snapshot(include_photo=include_photo)

        messages = []

        if include_photo and ctx.get("last_photo", {}).get("base64"):
            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": ctx["last_photo"]["base64"],
                        }
                    },
                    {"type": "text", "text": prompt}
                ]
            })
        else:
            ctx_str = json.dumps({k: v for k, v in ctx.items() if k != "last_photo"},
                                  ensure_ascii=False, default=str)
            messages.append({
                "role": "user",
                "content": f"Kontekst urządzenia:\n{ctx_str}\n\n{prompt}"
            })

        response = claude.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=messages
        )

        return {
            "text": response.content[0].text,
            "model": response.model,
            "tokens": response.usage.output_tokens,
            "context_summary": sensor_fusion.context_summary(ctx),
        }


# ── Wykonywanie akcji ─────────────────────────────────────────────────────────

async def execute_action(action: dict):
    """Wykonaj akcję zwróconą przez Claude"""
    act = action.get("action", "")
    log.info(f"Akcja: {act} — {json.dumps(action)}")

    if act == "send_sms":
        sms_sensor.send(action["to"], action["text"])

    elif act == "take_photo":
        from sensors import camera
        result = await asyncio.get_event_loop().run_in_executor(
            None, camera.capture, action.get("camera", "back")
        )
        log.info(f"Zdjęcie: {result.get('path', 'błąd')}")

    elif act == "alert_homelab":
        await _send_homelab_alert(action["message"])

    elif act == "shell":
        import subprocess
        try:
            out = subprocess.run(
                action["command"], shell=True,
                capture_output=True, text=True, timeout=30
            ).stdout[:500]
            log.info(f"Shell output: {out}")
        except Exception as e:
            log.error(f"Shell error: {e}")

async def _send_homelab_alert(message: str):
    if not HOMELAB_WEBHOOK:
        return
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            await session.post(HOMELAB_WEBHOOK, json={
                "agent": AGENT_NAME,
                "message": message,
                "timestamp": datetime.utcnow().isoformat()
            }, timeout=aiohttp.ClientTimeout(total=10))
    except Exception as e:
        log.debug(f"Homelab alert failed: {e}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_authorized(number: str) -> bool:
    if "*" in ALLOWED_NUMBERS:
        return True
    cleaned = number.replace(" ", "").replace("-", "")
    return any(cleaned.endswith(a.replace(" ", "").replace("-", "")) for a in ALLOWED_NUMBERS if a)


# ── Main loop ─────────────────────────────────────────────────────────────────

async def main():
    log.info(f"═══ {AGENT_NAME} startuje ═══")
    log.info(f"Claude API: {'✓' if ANTHROPIC_API_KEY else '✗ (brak klucza)'}")
    log.info(f"Sensory: GPS, SMS, kamera, ruch, audio, system")
    log.info(f"API server: port {API_PORT}")

    l2 = Level2Brain()
    l1 = Level1Engine(l2)

    # Uruchom API server w tle
    asyncio.create_task(_start_api_server(l2))

    iteration = 0
    while True:
        try:
            include_photo = False  # zdjęcie co N iteracji jeśli potrzebne
            ctx = await sensor_fusion.snapshot(include_photo=include_photo)

            summary = sensor_fusion.context_summary(ctx)
            if iteration % 6 == 0:  # log co minutę (6 * 10s)
                log.info(f"Context: {summary}")

            actions = await l1.process(ctx)
            for action in actions:
                await execute_action(action)

            iteration += 1
            await asyncio.sleep(SENSOR_INTERVAL)

        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error(f"Main loop error: {e}", exc_info=True)
            await asyncio.sleep(5)

    log.info(f"{AGENT_NAME} zatrzymany.")


async def _start_api_server(l2: Level2Brain):
    """Uruchamia FastAPI server (zaimportowany z api_server.py)"""
    try:
        import uvicorn
        from api_server import create_app
        app = create_app(l2)
        config = uvicorn.Config(app, host="0.0.0.0", port=API_PORT, log_level="warning")
        server = uvicorn.Server(config)
        await server.serve()
    except ImportError:
        log.warning("api_server.py nie znaleziony — API nie uruchomione")
    except Exception as e:
        log.error(f"API server error: {e}")


if __name__ == "__main__":
    def _shutdown(sig, frame):
        log.info("Shutdown signal")
        sys.exit(0)
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    asyncio.run(main())
