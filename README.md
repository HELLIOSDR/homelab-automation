# Helios — Autonomiczny AI Node na Samsung A23 5G

> _Mały telefon. Wielki mózg. Własna bateria, własny internet, własne zmysły._

## Co to jest?

Samsung Galaxy A23 5G przekształcony w **autonomiczny węzeł AI** z:
- **Claude API** jako mózgiem (dwupoziomowy: lokalny + pełny Claude)
- **Wszystkimi zmysłami**: GPS, kamera, mikrofon, akcelerometr, SMS/SIM
- **Własnym REST API** (kompatybilnym stylem z Anthropic API)
- **Trzy kanały dostępu**: SSH, ADB WiFi, reverse SSH tunnel
- **Pixel 2 XL identity** dla usług Google

## Architektura

```
[Homelab Server] <──SSH/ADB/RevTunnel──> [A23 5G — Magisk root]
                                            │
                                   [Termux Python Runtime]
                                            │
                              ┌─────────────┴──────────────┐
                              │       2-LEVEL AI BRAIN      │
                              │  Poziom 1: local rules      │
                              │  Poziom 2: Claude API       │
                              └─────────────┬──────────────┘
                                            │
                    GPS · Kamera · SMS · Mikrofon · Akcelerometr
```

## Szybki start

### 1. Sprawdź połączenie
```bash
bash scripts/adb/check_device.sh
```

### 2. Root (jeśli jeszcze nie)
```bash
bash scripts/root/prepare_root.sh
# (ręcznie patchuj boot.img w Magisk na telefonie)
bash scripts/root/flash_magisk.sh
bash scripts/root/verify_root.sh
```

### 3. Instaluj Termux + Python
```bash
bash scripts/termux/install_termux.sh
bash scripts/termux/setup_ssh.sh
```

### 4. Zainstaluj agenta na telefonie
```bash
# Spakuj i wypchnij agenta
tar -czf agent.tar.gz agent/
adb push agent.tar.gz /sdcard/ai_agent_latest.tar.gz

# Skonfiguruj
adb push config/.env.example /sdcard/
# Na telefonie w Termux: cp /sdcard/.env.example ~/ai_agent/.env && nano ~/ai_agent/.env
```

### 5. Uruchom
```bash
# Na telefonie (przez SSH lub ADB):
cd ~/ai_agent && python brain.py
```

## API

Telefon eksponuje API na porcie `7788`:

```bash
# Status
curl http://<phone-ip>:7788/v1/health

# Zapytaj AI z kontekstem sensorów
curl -X POST http://<phone-ip>:7788/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "gdzie jesteś?"}]}'

# Zdjęcie
curl http://<phone-ip>:7788/v1/photo > foto.jpg

# Snapshot sensorów
curl http://<phone-ip>:7788/v1/context

# Wyślij SMS
curl -X POST http://<phone-ip>:7788/v1/sms/send \
  -d '{"to": "+48XXXXXXXXX", "text": "Cześć!"}'
```

## SMS komendy

Wyślij SMS na numer SIM w telefonie:

```
co słychać?          → status + kontekst AI
patrz                → robi zdjęcie + analizuje
gdzie jesteś?        → GPS + opis miejsca
AI <dowolne pytanie> → pełna odpowiedź Claude
bateria              → poziom baterii
```

## Homelab Gateway

Na serwerze homelab:
```bash
# Skonfiguruj .env z PHONE_API_URL
cp config/.env.example config/.env

# Uruchom gateway
python homelab/sms_gateway.py

# Lub jako systemd service
sudo cp homelab/systemd/helios-gateway.service /etc/systemd/system/
sudo systemctl enable --now helios-gateway
```

## Struktura projektu

```
├── scripts/
│   ├── adb/          — detekcja urządzenia, ADB utils
│   ├── root/         — root przez Heimdall/Magisk
│   └── termux/       — instalacja i konfiguracja Termux
├── agent/
│   ├── brain.py      — główny agent (2-level AI)
│   ├── api_server.py — Claude-style REST API na telefonie
│   ├── sensor_fusion.py — unified sensor context
│   └── sensors/      — GPS, SMS, kamera, ruch, audio, system
├── homelab/
│   ├── sms_gateway.py — bridge na serwerze homelab
│   └── systemd/       — service files
└── config/
    ├── config.yaml   — konfiguracja agenta
    └── .env.example  — szablon sekretów
```

---

_Helios — zawsze z tobą, zawsze online._
