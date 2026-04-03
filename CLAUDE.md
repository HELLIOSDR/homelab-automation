# Helios — homelab-automation

Agent AI osadzony w telefonie (A23 5G). Działa w Termux.

## Architektura

```
brain.py          — główna pętla, Level1 (reguły) + Level2 (Claude API)
sensor_fusion.py  — zbiera wszystkie sensory równolegle, buduje unified context
autonomy.py       — watchdog, zarządzanie zasobami, proaktywna inteligencja
api_server.py     — FastAPI REST API na porcie 7788
sensors/          — GPS, SMS, kamera, ruch, audio, system
homelab/          — SMS gateway, usługi systemd
```

## Uruchomienie

```bash
make install   # zależności
make check     # składnia + testy
make run       # uruchom agenta
```

## Testy

```bash
make test                          # wszystkie
python3 -m pytest tests/test_autonomy.py -v   # konkretny moduł
```

## Zmienne środowiskowe

Skopiuj `config/.env.example` → `~/ai_agent/.env` i uzupełnij:
- `ANTHROPIC_API_KEY` — wymagany dla Level2
- `ALLOWED_NUMBERS` — numery z prawem do SMS komend
- `HOMELAB_WEBHOOK_URL` — webhook do homelaba

## Branch workflow

Zmiany → branch `claude/*` → PR → merge do master
Nie pushuj bezpośrednio na master.

## Sandbox

Przed zmianami: `/sandbox <opis>` — izolowany test z możliwością rollbacku.
Po zmianach: `/autonomy log` — historia operacji.
