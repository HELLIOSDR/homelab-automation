# Helios — homelab-automation

Agent AI osadzony w telefonie (A23 5G). Działa w Termux.

## Architektura

```
brain.py          — główna pętla, Level1 (reguły) + Level2 (Claude API)
sensor_fusion.py  — zbiera wszystkie sensory równolegle, unified context
autonomy.py       — watchdog, zasoby, proaktywna inteligencja
api_server.py     — FastAPI REST API port 7788
healthcheck.py    — self-test przed startem
sensors/          — GPS, SMS, kamera, ruch, audio, system
homelab/          — SMS gateway, systemd
scripts/          — heartbeat, cron, ADB, Termux setup
```

## Uruchomienie

```bash
make install        # zależności
make install-hooks  # git pre-push hook (blokuje push bez testów)
make check          # lint + testy (59 testów)
make healthcheck    # self-test środowiska
make run            # uruchom agenta
```

## Testy

```
tests/test_autonomy.py     — ResourceManager, ProactiveIntelligence, Identity (16)
tests/test_brain.py        — _is_authorized, Level1Engine (12)
tests/test_sensor_fusion.py — context_summary, get_current (8)
tests/test_sensors.py      — GPS, Motion, System sensors (14)
tests/test_sms_gateway.py  — Models, PhoneHelpers, Config (9)

Razem: 59 testów — 59/59 ✓
```

## Heartbeat (nie zasypiaj)

```bash
bash scripts/setup-cron.sh   # instaluje cron co 5 min
cat ~/.claude/heartbeat.log  # sprawdź czy żyje
```

## Zmienne środowiskowe

```
ANTHROPIC_API_KEY     — wymagany dla Level2
ALLOWED_NUMBERS       — numery z prawem do SMS komend
HOMELAB_WEBHOOK_URL   — webhook do homelaba (+ heartbeat)
```
Skopiuj `config/.env.example` → `~/ai_agent/.env`

## Workflow

```
zmiana → /sandbox → testy → PR → merge master
```

Nie pushuj bezpośrednio na master.
Pre-push hook blokuje push bez zielonych testów.

## Skills

```
/sandbox <opis>     — izolowany test z rollbackiem
/autonomy <zadanie> — praca autonomiczna przez sandbox
/autonomy log       — historia operacji
/autonomy rollback  — cofnij ostatnią zmianę
```
