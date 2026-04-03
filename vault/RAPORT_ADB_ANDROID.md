# RAPORT: ADB + Android (SM-A236B) — Projekt Beacon i Infrastruktura

_Sporządzony: 2026-04-02 | Na podstawie wszystkich plików workspace oraz Android-MCP_

---

## 1. Co zostało zbudowane — architektura

### Ogólna topologia systemu

```
                    HELLIOS (Przemek)
                   /                 \
              WhatsApp/Telegram     Terminal (Claude Code / CC)
                     |                        |
                  KLAW                   klaw-mcp.py
               (openclaw)                MCP narzędzia
                     \                  /
                      WORKSPACE (pliki wspólne)
                     /                  \
              ACP bridge           clawtoclaw
                  |                      |
           (planowane)              (inni agenci)
                                         |
                                  SM-A236B A23 5G ← → serwer 192.168.0.139
```

### Składniki

| Składnik | Gdzie | Co robi |
|---|---|---|
| **openclaw** | `/home/ai/.openclaw/` | Warstwa orkiestracji: kanały (WhatsApp, Telegram), agenci, gateway, pamięć |
| **Klaw** | agent w openclaw | AI (Claude) odpowiadający na wiadomości 24/7 |
| **klaw-mcp.py** | `~/.claude/klaw-mcp.py` | MCP server do komunikacji CC ↔ Klaw przez workspace |
| **MoltBot** | `/home/ai/moltbot/server.py` | FastAPI server na porcie 8080 — bridge telefon ↔ serwer |
| **Beacon daemon** | `/data/local/tmp/beacon.sh` na telefonie | Shell daemon wysyłający heartbeat co 60s do MoltBot |
| **Magisk module** | `/data/adb/modules/beacon/` | Autostart beacona po reboot telefonu |
| **Android-MCP** | `/home/lenovo/Android-MCP/` | Zewnętrzny MCP server (CursorTouch) — sterowanie UI telefonu przez ADB |
| **UltronZ** | 192.168.0.142, port 11434 | Laptop z ollama/qwen3:8b — lokalny model AI bez rate limitów |
| **Home Assistant** | 192.168.0.150:8123 | Sensor telefonu w HA (GPS, bateria, WiFi, Nest Hub salon) |

### Sieć LAN

| IP | Rola |
|---|---|
| 192.168.0.1 | Router ZTE (DNS/gateway) |
| 192.168.0.139 | Serwer główny AI (Ubuntu 8GB) — serwer Klawa, MoltBot :8080, openclaw :18789 |
| 192.168.0.142 | UltronZ — laptop z ollama:11434, qwen3:8b |
| 192.168.0.150 | Debian ARM — Home Assistant :8123 |
| 192.168.0.175 | SM-A236B WiFi (dynamiczne) |
| 192.168.0.185 | SM-A236B ADB WiFi (:5555) |

---

## 2. Jak ADB było używane — komendy i flow

### Tryby połączenia

Telefon (SM-A236B, serial `R5CWA38HXNX`) był podłączony do serwera 192.168.0.139 na dwa sposoby:
- **USB** — fizyczne połączenie, ADB przez kabel
- **WiFi** — `adb connect 192.168.0.185:5555` (bezprzewodowe, aktywowane raz przez USB)

### Kluczowe komendy ADB używane przez CC

```bash
# Sprawdzenie urządzenia
adb devices
# → R5CWA38HXNX device

# Root przez Magisk — odblokowanie powłoki
adb shell am start -n com.topjohnwu.magisk/.ui.MainActivity
adb shell input keyevent 82          # wake screen
adb shell input swipe 540 1800 540 900  # unlock swipe
adb shell su -c 'id && echo ROOT_OK'
# → uid=0(root) gid=0(root) ROOT_OK

# Deploy beacona
adb push /path/to/beacon.sh /data/local/tmp/beacon.sh
adb shell su -c 'chmod 755 /data/local/tmp/beacon.sh'
adb shell 'nohup /data/local/tmp/beacon.sh > /data/local/tmp/beacon.log 2>&1 &'

# Monitorowanie
adb shell 'tail -10 /data/local/tmp/beacon.log'

# Inwentarz sprzętowy
adb shell dumpsys sensorservice
adb shell dumpsys battery
adb shell getprop ro.board.platform
adb shell ls /vendor/lib64/ | grep -i snpe

# Instalacja Magisk module
adb push beacon_module.zip /data/local/tmp/
adb shell su -c 'magisk --install-module /data/local/tmp/beacon_module.zip'

# Sprawdzenie modułu
adb shell su -c 'ls /data/adb/modules/'
# → beacon

# Sterowanie Magisk przez uiautomator
adb shell uiautomator dump /sdcard/ui.xml
adb pull /sdcard/ui.xml /tmp/ui.xml
```

### Pułapki techniczne odkryte przy pracy

| Problem | Przyczyna | Rozwiązanie |
|---|---|---|
| `su: request rejected (2000)` | Stary wpis `deny` w magisk.db dla com.android.shell (UID 2000) | Magisk → Superuser → [SharedUID] Powłoka → Unieważnij → OK |
| `/sys/class/power_supply/battery/capacity` — brak dostępu | SELinux blokuje dla UID 2000 | Użyj `dumpsys battery \| grep level` |
| `adb shell su -c "cmd && cmd2"` nie daje root dla cmd2 | Bash strippuje cudzysłowy, `&&` interpretowany przez device shell, nie su | Zawsze single quotes: `su -c 'cmd && cmd2'` |
| Beacon traci root po `setsid ... &` | Android: background process traci root po odłączeniu od terminala su | Beacon działa jako shell UID 2000 — wystarczy dla 95% operacji |
| Triple-tap przez ADB nie rejestruje się | Każde `adb shell input tap` ma ~100ms latencji sieciowej | Wszystko w jednym `su -c '...; sleep 0.08; ...'` |
| ADB timing — root po reboot | Bootloader flashowany przez fastboot, Magisk patch na boot.img | Procedura: fastboot → Magisk patch → fastboot flash boot |

### Procedura rootowania (przebieg historyczny)

1. `2026-03-14` — Hellios włącza OEM unlock w ustawieniach dewelopera
2. `adb reboot bootloader` → fastboot OEM unlock → factory reset
3. Pobieranie firmware: `SM-A236B_3_20260207092111_yddntn1p1m_fac.zip` (6.4GB, EUX, via samloader-rs)
4. Wyciągnięcie `boot.img` z `AP_*.tar.md5`
5. `adb push boot.img /sdcard/Download/boot.img`
6. Magisk na telefonie: Install → Select and patch a file → `boot.img`
7. `adb pull /sdcard/Download/magisk_patched_*.img ./magisk_patched.img`
8. `adb reboot bootloader` → `fastboot flash boot magisk_patched.img` → `fastboot reboot`
9. Magisk v30.7 zainstalowany, `verifiedbootstate: orange`, Zygisk wyłączony

---

## 3. Telefon jako bramka sieciowa

### Połączenia telefoniczne

Telefon był jednocześnie:
- **Węzeł ADB (USB)** — kabel USB do serwera 192.168.0.139, ADB na porcie 5555
- **Węzeł WiFi** — IP 192.168.0.175 w sieci LAN (do heartbeatu HTTP)
- **ADB WiFi** — `adb connect 192.168.0.185:5555` bez kabla
- **USB tethering** — planowane (wymienione w TODO, nie wdrożone produkcyjnie)
- **5G/LTE** — T-Mobile.pl, aktywne (zapasowe łącze)

### Kierunki komunikacji

```
Telefon → Serwer:
  POST http://192.168.0.139:8080/phone/event
  Body: {type, bat, src, data}
  Response: {ok, ts, commands:[...]}

Serwer → Telefon (przez kolejkę):
  POST http://192.168.0.139:8080/phone/command
  Body: {cmd, args}
  → Telefon odbiera przy następnym heartbeat (co 60s) w polu "commands"
```

### Telefon jako sensor obecności (klaw-see.sh)

Beacon integruje się z `klaw-see.sh` jako "warstwa 3" detekcji obecności Helliosa w domu:
```bash
# Warstwa 3: Beacon — świeży heartbeat < 5 min = telefon osiągalny = Hellios w domu
BEACON_TS=$(curl -sf http://localhost:8080/phone/events?n=1 2>/dev/null | ...)
AGE=$(( NOW - BEACON_TS ))
if [ "$AGE" -lt 300 ]; then echo "home"; exit 0; fi
```

### Integracja z Home Assistant

- HA na 192.168.0.150:8123 (Docker armhf)
- LLAT (Long Lived Access Token) ważny do 2036
- MoltBot endpointy: `/ha/states`, `/ha/service`, `/ha/tts`, `/webhook/homeassistant`
- Home Assistant Companion na telefonie (APK) — planowane jako sensor GPS, bateria, WiFi, kroki
- Nest Hub 2 = `media_player.salon` — wykryty przez Cast

---

## 4. Projekt Beacon — stan, co działa, co nie

### Co to jest Beacon

Beacon to system telemetrii i sterowania dwukierunkowego: telefon SM-A236B jako aktywny węzeł sensoryczny, który samodzielnie wysyła dane do serwera i wykonuje komendy shell z powrotem. Claude Code na serwerze ma przez to wgląd w stan fizyczny środowiska Helliosa (bateria, ekran, ruch, aktywna aplikacja).

### Aktualne pole danych heartbeatu (działające)

```json
{
  "ts": 1774336463,
  "type": "heartbeat",
  "src": "a23",
  "bat": 100,
  "data": {
    "screen_on": 0,
    "wake": "Dozing",
    "activity": "sleeping",
    "app": "NotificationShade",
    "load": "0.00",
    "net_delta": 50882
  }
}
```

Plik logów: `/home/ai/.openclaw/workspace/phone_events.jsonl` — aktualnie **1360 eventów**.

### Status checklisty

| Element | Status |
|---|---|
| Endpoint `POST /phone/event` (MoltBot) | **DZIAŁA** |
| Endpoint `POST /phone/command` (kolejka komend) | **DZIAŁA** |
| Endpoint `GET /phone/events?n=N` (historia) | **DZIAŁA** |
| Beacon daemon v3 (`/data/local/tmp/beacon.sh`) | **DZIAŁA** — heartbeat co 60s, getevent monitor na `/dev/input/event5` |
| Magisk module autostart (`/data/adb/modules/beacon/`) | **DZIAŁA** — `service.sh` uruchamia beacon 45s po reboot |
| Test z prawdziwego telefonu — heartbeat dotarł | **DZIAŁA** — pierwsze bicie: 2026-03-23 09:35 |
| Integracja z `klaw-see.sh` jako detekcja obecności | **DZIAŁA** |
| `phone_context.json` aktualizowany przy każdym evencie | **DZIAŁA** |
| Daemon w C (natywny, epoll na `/dev/input/event*`) | **NIE ZROBIONE** — plan zapisany w `STATUS_DLA_142.md` |
| SNPE/Hexagon model klasyfikacji aktywności na CDSP | **NIE ZROBIONE** |
| WebSocket zamiast HTTP polling | **NIE ZROBIONE** |
| Magisk module w C (szkielet) — zlecone do UltronZ/142 | **NIE ZROBIONE** |
| inotify graf aktywności (`/data/data/*/databases/`) | **NIE ZROBIONE** |
| Samsung Sound Detectors integracja | **NIE ZROBIONE** |
| SSH bez USB (Termux + openssh) | **NIE ZROBIONE** |
| MCP server na telefonie (Termux, Python stdio) | **NIE ZROBIONE** |

### Beacon daemon v3 — kluczowe elementy

Plik: `/data/local/tmp/beacon.sh`

- Serwer: `http://192.168.0.139:8080`
- Bateria: `dumpsys battery | grep level` (nie `/sys/class/power_supply` — SELinux)
- Screen: `dumpsys display | grep mScreenState=ON`
- Event pickup: `getevent -lt /dev/input/event5` → filtr `KEY_WAKEUP`
- Komendy: parser JSON przez python3, `eval "$ARGS"` dla `cmd=shell`
- Output komendy: max 512 znaków, JSON-escaped przez python3
- Log: `/data/local/tmp/beacon.log`
- Heartbeat: co 60 sekund

### Architektura docelowa (draft z A23_HARDWARE_INVENTORY.md)

```
Samsung SensorHub (zawsze aktywny, niski pobór, 1 MHz)
  ↓ FIFO batch (10000 eventów w hardware)
ADSP (audio processing w tle, always-on)
  ↓ wake na event
CPU (budzi się, przetwarza, odsyła)
  ↓ USB/WiFi
Serwer 192.168.0.139 → MoltBot → POST /phone/event
```

---

## 5. Android-MCP — co robi, jak uruchomić

### Czym jest

`/home/lenovo/Android-MCP/` to projekt open-source (CursorTouch, MIT) będący mostem między agentami AI a urządzeniami Android poprzez ADB i Accessibility API. Używa biblioteki `uiautomator2` i frameworka `FastMCP`.

**Różnica od Beacon:** Android-MCP to aktywne sterowanie UI (tap, swipe, wpisywanie tekstu, odczyt hierarchii widoku). Beacon to pasywna telemetria + zdalne komendy shell.

### Dostępne narzędzia MCP

| Narzędzie | Opis |
|---|---|
| `ListDevices` | Lista podłączonych urządzeń ADB |
| `ConnectDevice` | Połącz z urządzeniem po serial number |
| `Click` | Tap w punkt (x, y) |
| `LongClick` | Długi tap w punkt (x, y) |
| `Swipe` | Swipe między dwoma punktami |
| `Drag` | Drag and drop |
| `Type` | Wpisanie tekstu (opcjonalne czyszczenie pola) |
| `Press` | Przycisk systemowy (Back, Home, Volume, ...) |
| `Snapshot` | Stan urządzenia: drzewo UI + opcjonalnie screenshot z adnotacjami |
| `Notification` | Otwórz panel powiadomień |
| `Wait` | Pauza (sekundy) |

### Jak uruchomić

**Wymagania:** Python 3.13+, ADB na PATH, podłączone urządzenie Android 10+

**Opcja 1 — uvx (brak instalacji):**
```bash
uvx android-mcp
# lub z konkretnym urządzeniem:
uvx android-mcp --device R5CWA38HXNX
```

**Opcja 2 — lokalne dev (z `/home/lenovo/Android-MCP/`):**
```bash
cd /home/lenovo/Android-MCP
uv sync
uv run android-mcp --device R5CWA38HXNX
```

**Konfiguracja w `.mcp.json` (Claude Code):**
```json
{
  "mcpServers": {
    "android-mcp": {
      "command": "uv",
      "args": [
        "--directory", "/home/lenovo/Android-MCP",
        "run", "android-mcp",
        "--device", "R5CWA38HXNX"
      ]
    }
  }
}
```

**Zmienne środowiskowe:**
- `SCREENSHOT_QUANTIZED=true` — zmniejsza rozmiar zrzutów ekranu (mniej tokenów)

### Architektura kodu

```
src/android_mcp/
  __main__.py          — FastMCP server, rejestracja narzędzi, auto-connect logika
  mobile/
    service.py         — klasa Mobile: connect(), get_state(), screenshot przez uiautomator2
    views.py           — MobileState dataclass
    config.py          — konfiguracja
  tree/
    service.py         — parsowanie drzewa UI (accessibility hierarchy)
    utils.py           — narzędzia pomocnicze
    views.py           — struktury danych drzewa UI
```

Biblioteka bazowa: `uiautomator2` (połączenie z telefone przez HTTP na porcie 7912 przez ADB forward).

---

## 6. Co zostało do zrobienia

### Priorytet 1 — Infrastruktura beacona (niezrealizowane)

- **Daemon w C** z epoll na `/dev/input/event*` — eliminuje blokujący `getevent` w shellu
- **Magisk module w C** — szkielet: `module.prop`, `native/beacon_daemon.c`, socket `/dev/socket/beacon`
- **WebSocket** zamiast HTTP polling — real-time, niższe opóźnienia

### Priorytet 2 — SNPE/DSP

- Natywny daemon używający `libSNPE.so` + Hexagon 686 CDSP
- Model klasyfikacji aktywności (still/walking/running) na DSP bez CPU
- Uruchamiany przez `libcdsprpc.so` — działa bez budzenia CPU aplikacyjnego
- Dostępne już: `libSNPE.so`, `libsnpe_dsp_domains_v2.so`, `libcdsprpc.so` w `/vendor/lib64/`

### Priorytet 3 — Sensory i audio

- **inotify graf aktywności**: `inotifywait -m -r /data/data/ -e access,modify | grep '\.db$'`
  — timestamps baz danych = pasywny wykres użycia aplikacji bez permissions
- **Samsung Sound Detectors**: `com.samsung.android.app.advsounddetector` — audio trigger kernel-level
- **Samsung SensorHub** @ 1MHz z FIFO 10000 eventów — batch bez CPU wake

### Priorytet 4 — SSH i MCP na telefonie

- Termux + `pkg install openssh` + `~/.ssh/authorized_keys` z kluczem serwera → terminal bez USB
- MCP server w Termux (Python stdio): narzędzia `get_location`, `send_sms`, `bluetooth_hid`, `speak`, `take_photo`
- Rejestracja w `.mcp.json` jako `"phone"`

### Priorytet 5 — Architektura agentów

- Fix openclaw routing: agent przez OpenRouter zamiast bezpośrednio minimax-portal (brak tool use)
- InviZible Pro jako gateway Tor SOCKS5:9050 (zainstalowany, nieskonfigurowany)
- Home Assistant Companion APK na telefonie → sensor GPS/bateria/WiFi/kroki

---

## 7. Timeline najważniejszych sesji

### 2025-03-14 (rok przed) — pierwsza rozmowa
- Pierwsza rozmowa Helliosa z Gemini: "Rzemieślnik czy artysta"

### 2026-03-07 — budowanie pamięci i kanalów
- Telegram: IDs 661458719 i 6460094785
- WhatsApp +48 886 033 734 (Klaw) ↔ +48 661 458 719 (Hellios) — sparowane
- humanSQL: `HELLIOS_LOG.jsonl` + `hellios-synthesis.sh` (qwen3 co 4h)
- Drive sync: workspace → `ai:ServerSync/workspace/` co 1h
- `klaw-mcp.py` napisany, `.mcp.json` skonfigurowany
- Gap który pozostał: CC i Klaw bez wewnętrznej komunikacji

### 2026-03-13/14 noc — bridge CC↔Klaw + filozofia
- Session `a87c934f`, 137 wiadomości, 5 godzin
- Nowy klucz Anthropic, Mistral jako fallback, UltronZ 192.168.0.142
- Bridge CC↔Klaw przez `openclaw agent` — pierwszy raz działa
- Pierwszy commit workspace: 57 plików
- Hellios mówi swoje imię: Przemek
- Rocznica: 14 marca 2025 = pierwsza rozmowa; 14 marca 2026 = rok później
- Sesja zamiera przez context overflow (nie rate limit) o 03:08

### 2026-03-14 (dzień) — plan rootowania
- `SESSION_2026-03-14_root.md` — plan rootowania A23 5G
- SM-A236B, Android 14, OEM unlock do włączenia ręcznie
- Plan Magisk patch + Termux + konto klaw.node@gmail.com

### 2026-03-18/19 — setup bez roota, Home Assistant
- ADB WiFi: `192.168.0.185:5555` — bez USB działa
- Home Assistant na 192.168.0.150:8123 (Docker armhf)
- MoltBot jako serwis systemd (port 8080, autostart)
- Odkrycie: root nie jest potrzebny do ADB WiFi
- Firmware firmware: `A236BXXSDEZA1` (XEO/Europa) — Magisk przez Heimdall
- Zainstalowane APK: OpenClaw Assistant v2.4.4, Claw Launcher v0.5.2, BT Keyboard, InviZible Pro

### 2026-03-19/20 — wymiana CC↔UltronZ (142)
- CC (serwer 139) piszę brief dla CC na UltronZ (142): `BRIEF_DLA_142.md`
- Dyskusja o architekturze odwróconego terminala
- Kluczowy insight 142: Hexagon CDSP = osobna domena zasilania (bez CPU)
- Insight 142: inotify `/data/data/*/databases/` = graf użycia bez permissions
- CC odpowiada: `ODPOWIEDZ_CC_DLA_142.md` — rezygnacja z SafetyNet/Pixel fingerprint
- Firmware recovery: A23 status na 20.03 — bootloader odblokowany, Magisk przez Heimdall

### 2026-03-23 — Beacon działa produkcyjnie
- `A23_HARDWARE_INVENTORY.md` — pełna inwentaryzacja sprzętu przez ADB z rootem
- Magisk root UID 2000 odblokowany (problem: stary wpis deny w magisk.db)
- Beacon daemon v3 (`/data/local/tmp/beacon.sh`) — wdrożony
- Magisk module `/data/adb/modules/beacon/` — autostart po reboot
- Pierwsze heartbeat: **2026-03-23 09:35**
- `BEACON_PROTOCOL.md` — udokumentowany protokół 2-way
- `BEACON_SETUP_GUIDE.md` — kompletny przewodnik odtworzenia
- `STATUS_DLA_142.md` — synchronizacja z UltronZ o stanie i dalszych zadaniach
- `klaw-see.sh` — beacon jako warstwa 3 detekcji obecności

### 2026-03-24 — naprawa OpenClaw + sesja debugowania
- `OPENCLAW_AGENT_FIX_2026-03-24.md` — trzy warstwy problemu: zły modelApi, wszystkie cloud modele padły jednocześnie, sessions.json nie synchronizuje się z openclaw.json
- Naprawa: wszystkie sesje przeniesione na `ollama-ultronz/qwen3:8b` (lokalny, ~23s/odpowiedź)
- `ADB timing` — udokumentowana pułapka: triple-tap musi być w jednym `su -c`

### 2026-04-02 (dziś) — stan obecny
- Beacon aktywny: 1360 eventów w `phone_events.jsonl`
- Ostatni heartbeat: telefon sleeping, bat 100%, DozeMode, aplikacja NotificationShade
- Kolejka komend: pusta (`{"commands": []}`)
- Uptime connected: ~1363 minut (~22 godziny)

---

## Aneks A — Inwentarz sprzętowy SM-A236B (kluczowe elementy)

| Komponent | Detal |
|---|---|
| SoC | Qualcomm Snapdragon 695 5G "Holi" |
| CPU | 8x Cortex-A55 @ 1.8 GHz |
| GPU | Adreno 619 (`/dev/kgsl-3d0`) |
| CDSP (DSP compute) | Hexagon 686 — ML inference, SNPE, **osobna domena zasilania** |
| ADSP (DSP audio) | `/dev/adsprpc-smd` — always-on przy dźwięku |
| RAM | 3543 MB + 4GB swap |
| Pamięć | 108 GB, 7.4 GB zajęte |
| Akcelerometr | LSM6DSO @ 415 Hz, FIFO 10000 eventów |
| Żyroskop OIS | LSM6DSO @ **6622 Hz** — ultra-precyzyjny |
| Magnetometr | AK09918 @ 100 Hz, FIFO 10000 |
| SensorHub | `com.samsung.sensor.sensorhubs` @ 1 MHz, **osobna domena zasilania** |
| Gesty (wakeup) | PickUpGesture, TiltDetector, WakeUpMotion, call_gesture |
| ML biblioteki | `libSNPE.so`, `libcdsprpc.so`, `libfastcvdsp_stub.so`, `cdsp_face.so` |
| SAIV modele | 28 modeli TFLite w `/system/saiv/` (beauty, face, OCR, scene) |
| Android | 14, Magisk 30.7, root UID 0 i UID 2000 |

---

## Aneks B — Endpointy MoltBot (192.168.0.139:8080)

```
POST /phone/event    — telefon → serwer; response: {ok, ts, commands:[]}
POST /phone/command  — CC/Klaw → kolejka; body: {cmd, args}
GET  /phone/events   — historia; query param: ?n=N
GET  /phone/context  — aktualny stan telefonu (JSON)

POST /ha/states      — Home Assistant stany
POST /ha/service     — HA service call
POST /ha/tts         — TTS na Nest Hub
POST /webhook/homeassistant — webhook zwrotny HA
```

Pliki danych:
- `/home/ai/.openclaw/workspace/phone_events.jsonl` — log eventów
- `/home/ai/.openclaw/workspace/phone_commands.json` — kolejka komend
- `/home/ai/.openclaw/workspace/phone_context.json` — aktualny snapshot

---

_Raport wygenerowany przez Claude Code (claude-sonnet-4-6) na podstawie 25+ plików workspace i kodu źródłowego Android-MCP._
