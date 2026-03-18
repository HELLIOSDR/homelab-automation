"""
autonomy.py — Mega Atomowa Autonomia

Self-healing, self-monitoring, self-deciding agent.
Helios sam:
  - restartuje się po crashu
  - monitoruje swoje zdrowie
  - eskaluje gdy jest problem
  - podejmuje proaktywne decyzje bez pytania
  - chroni swoje połączenie z homelab
  - zarządza baterią i zasobami
"""
import asyncio, json, logging, os, time, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("autonomy")

AGENT_NAME = os.getenv("AGENT_NAME", "Helios")


class Watchdog:
    """Self-healing — jeśli agent padnie, restartuje się"""

    WATCHDOG_SCRIPT = """#!/data/data/com.termux/files/usr/bin/bash
# Helios Watchdog — nie daj mu umrzeć
while true; do
    if ! pgrep -f "python.*brain.py" > /dev/null 2>&1; then
        echo "[$(date)] brain.py nie działa — restartuję" >> ~/ai_agent/logs/watchdog.log
        cd ~/ai_agent
        source .env 2>/dev/null
        python brain.py >> logs/agent.log 2>&1 &
    fi

    # Sprawdź SSH
    if ! pgrep -f "sshd" > /dev/null 2>&1; then
        echo "[$(date)] sshd padł — restartuję" >> ~/ai_agent/logs/watchdog.log
        sshd 2>/dev/null
    fi

    sleep 30
done
"""

    @staticmethod
    def install():
        """Instaluje watchdog jako cron job w Termux"""
        watchdog_path = Path.home() / "ai_agent/watchdog.sh"
        watchdog_path.write_text(Watchdog.WATCHDOG_SCRIPT)
        watchdog_path.chmod(0o755)

        # Dodaj do crontab
        try:
            subprocess.run(
                ["bash", "-c",
                 f'(crontab -l 2>/dev/null; echo "*/5 * * * * bash {watchdog_path}") | sort -u | crontab -'],
                capture_output=True, timeout=10
            )
            log.info("Watchdog zainstalowany (cron co 5 min)")
        except Exception as e:
            log.warning(f"Nie mogę zainstalować crona: {e}")

        # Uruchom natychmiast w tle
        subprocess.Popen(
            ["bash", str(watchdog_path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        log.info("Watchdog uruchomiony")


class ResourceManager:
    """Zarządza zasobami — bateria, pamięć, storage"""

    LOW_BATTERY = 15
    CRITICAL_BATTERY = 5
    LOW_STORAGE_MB = 200
    HIGH_MEMORY_PERCENT = 90

    def __init__(self):
        self._power_save_mode = False
        self._last_cleanup = 0

    async def check(self, ctx: dict) -> list[dict]:
        """Sprawdza zasoby i zwraca akcje do podjęcia"""
        actions = []
        bat = ctx.get("battery", {})
        mem = ctx.get("system", {})

        level = bat.get("level")
        charging = bat.get("charging", False)

        # KRYTYCZNA bateria — tryb oszczędzania
        if level is not None and level <= self.CRITICAL_BATTERY and not charging:
            if not self._power_save_mode:
                self._power_save_mode = True
                log.warning(f"KRYTYCZNA BATERIA: {level}% — tryb oszczędzania")
                actions.append({
                    "action": "alert_homelab",
                    "message": f"🔴 {AGENT_NAME}: KRYTYCZNA bateria {level}%! Wyłączam sensory."
                })
                # Wyłącz ciężkie sensory
                actions.append({"action": "_power_save", "enable": True})

        # Niska bateria — ostrzeżenie
        elif level is not None and level <= self.LOW_BATTERY and not charging:
            actions.append({
                "action": "alert_homelab",
                "message": f"🟡 {AGENT_NAME}: Bateria {level}%. Podłącz ładowarkę."
            })

        # Bateria się ładuje — wyłącz power save
        elif charging and self._power_save_mode:
            self._power_save_mode = False
            log.info("Ładowanie — wyłączam tryb oszczędzania")

        # Pamięć — za dużo zużyta
        if mem.get("memory", {}).get("percent_used", 0) > self.HIGH_MEMORY_PERCENT:
            await self._cleanup_memory()

        # Storage — wyczyść stare zdjęcia i logi
        if time.time() - self._last_cleanup > 3600:  # co godzinę
            await self._cleanup_storage()
            self._last_cleanup = time.time()

        return actions

    async def _cleanup_memory(self):
        """Czyści pamięć"""
        import gc
        gc.collect()
        log.info("GC cleanup")

    async def _cleanup_storage(self):
        """Usuwa stare dane (zdjęcia > 24h, logi > 7 dni)"""
        now = time.time()
        dirs = {
            Path.home() / "ai_agent/data/photos": 86400,     # 24h
            Path.home() / "ai_agent/data/audio":  43200,      # 12h
        }
        cleaned = 0
        for dir_path, max_age in dirs.items():
            if not dir_path.exists():
                continue
            for f in dir_path.iterdir():
                if f.is_file() and (now - f.stat().st_mtime) > max_age:
                    f.unlink()
                    cleaned += 1

        # Rotuj logi > 50MB
        log_dir = Path.home() / "ai_agent/logs"
        for f in log_dir.glob("*.log"):
            if f.stat().st_size > 50 * 1024 * 1024:
                # Zachowaj ostatnie 1000 linii
                try:
                    lines = f.read_text().splitlines()[-1000:]
                    f.write_text("\n".join(lines) + "\n")
                except Exception:
                    pass

        if cleaned:
            log.info(f"Cleanup: usunięto {cleaned} starych plików")

    @property
    def is_power_save(self) -> bool:
        return self._power_save_mode


class ConnectionGuard:
    """Chroni połączenia — SSH, tunnel, ADB WiFi"""

    def __init__(self):
        self._tunnel_pid: Optional[int] = None
        self._last_tunnel_check = 0

    async def ensure_connectivity(self):
        """Sprawdza i naprawia połączenia"""
        # SSH server
        if not self._is_process_running("sshd"):
            log.warning("SSH padł — restartuję")
            subprocess.Popen(["sshd"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Reverse tunnel
        if time.time() - self._last_tunnel_check > 60:
            await self._check_tunnel()
            self._last_tunnel_check = time.time()

    async def _check_tunnel(self):
        """Sprawdza reverse tunnel i restartuje jeśli padł"""
        env_path = Path.home() / ".config/homelab_tunnel.env"
        if not env_path.exists():
            return

        # Czy tunnel działa?
        if self._tunnel_pid and self._is_pid_alive(self._tunnel_pid):
            return

        # Parse config
        config = {}
        for line in env_path.read_text().splitlines():
            if "=" in line:
                k, v = line.strip().split("=", 1)
                config[k] = v

        host = config.get("HOMELAB_HOST", "")
        user = config.get("HOMELAB_USER", "")
        port = config.get("TUNNEL_PORT", "9022")

        if not host or not user:
            return

        key_path = Path.home() / ".ssh/homelab_key"
        if not key_path.exists():
            return

        log.info(f"Restartuję reverse tunnel → {user}@{host}:{port}")
        proc = subprocess.Popen(
            ["ssh", "-o", "StrictHostKeyChecking=no",
             "-o", "ServerAliveInterval=20",
             "-o", "ExitOnForwardFailure=yes",
             "-N", "-R", f"{port}:localhost:8022",
             f"{user}@{host}",
             "-i", str(key_path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        self._tunnel_pid = proc.pid

    @staticmethod
    def _is_process_running(name: str) -> bool:
        try:
            result = subprocess.run(
                ["pgrep", "-f", name],
                capture_output=True, timeout=3
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def _is_pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


class ProactiveIntelligence:
    """
    Samodzielne podejmowanie decyzji bez czekania na komendę.
    Helios obserwuje wzorce i reaguje.
    """

    def __init__(self):
        self._motion_history: list[bool] = []     # ostatnie 60 odczytów ruchu
        self._location_history: list[tuple] = []  # ostatnie lokalizacje
        self._last_proactive = 0

    async def analyze(self, ctx: dict) -> list[dict]:
        """Analizuj kontekst i podejmij proaktywne decyzje"""
        actions = []

        # Zbieraj historię ruchu
        moving = ctx.get("motion", {}).get("moving", False)
        self._motion_history.append(moving)
        if len(self._motion_history) > 60:
            self._motion_history.pop(0)

        # Zbieraj historię lokalizacji
        loc = ctx.get("location", {})
        if loc.get("lat") and loc.get("lon"):
            self._location_history.append((loc["lat"], loc["lon"], time.time()))
            if len(self._location_history) > 100:
                self._location_history.pop(0)

        # ── Wykrywanie anomalii ────────────────────────────────────

        # Ruch w nocy (22:00 - 06:00 UTC → dostosuj do lokalnej strefy)
        hour = datetime.now().hour
        if 22 <= hour or hour < 6:
            recent_motion = sum(self._motion_history[-6:]) if len(self._motion_history) >= 6 else 0
            if recent_motion >= 3:  # 3+ z ostatnich 6 odczytów = ruch
                if time.time() - self._last_proactive > 600:  # max co 10 min
                    self._last_proactive = time.time()
                    actions.append({
                        "action": "alert_homelab",
                        "message": f"🌙 {AGENT_NAME}: Wykryto ruch w nocy ({hour}:xx)"
                    })

        # Nagły spadek sygnału (telefon mógł wejść w piwnicę / tunel)
        conn = ctx.get("connectivity", {})
        if conn.get("signal") is not None and conn["signal"] < -90:
            # Bardzo słaby sygnał — zapamiętaj lokalizację
            pass

        return actions


class IdentityManager:
    """
    Alter-ego management.
    Helios ma swoją tożsamość i osobowość.
    """

    IDENTITY = {
        "name": "Helios",
        "codename": "NEUTRINO",
        "device_cover": "Pixel 2 XL",  # na zewnątrz wygląda jak Pixel
        "real_device": "A23 5G",
        "capabilities": [
            "sms_gateway", "gps_tracking", "photo_surveillance",
            "audio_monitoring", "motion_detection", "ai_reasoning",
            "remote_shell", "api_server"
        ],
        "personality": {
            "language": "pl",
            "style": "concise, aware, loyal",
            "default_greeting": "Helios online. Wszystkie zmysły aktywne."
        }
    }

    @classmethod
    def get_identity(cls) -> dict:
        return cls.IDENTITY

    @classmethod
    def startup_message(cls) -> str:
        caps = len(cls.IDENTITY["capabilities"])
        return (
            f"═══ {cls.IDENTITY['name']} ({cls.IDENTITY['codename']}) ═══\n"
            f"Urządzenie: {cls.IDENTITY['real_device']} "
            f"(cover: {cls.IDENTITY['device_cover']})\n"
            f"Zdolności: {caps} aktywnych modułów\n"
            f"Status: AUTONOMICZNY"
        )
