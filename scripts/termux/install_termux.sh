#!/usr/bin/env bash
# install_termux.sh — Instaluje Termux + Termux:API + Termux:Boot przez ADB
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APK_DIR="${SCRIPT_DIR}/../../.apks"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
die()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }

DEVICE=$(adb devices | grep -v "List of devices" | grep "device$" | awk '{print $1}' | head -1)
[[ -z "$DEVICE" ]] && die "Brak urządzenia ADB"
log "Urządzenie: $DEVICE"

mkdir -p "$APK_DIR"

# Pobierz APKi (F-Droid builds — bez Google Play)
declare -A APKS=(
    ["termux"]="https://f-droid.org/repo/com.termux_1020.apk"
    ["termux-api"]="https://f-droid.org/repo/com.termux.api_51.apk"
    ["termux-boot"]="https://f-droid.org/repo/com.termux.boot_7.apk"
)

for name in "${!APKS[@]}"; do
    APK_FILE="${APK_DIR}/${name}.apk"
    if [[ ! -f "$APK_FILE" ]]; then
        log "Pobieram $name..."
        curl -L "${APKS[$name]}" -o "$APK_FILE" || {
            warn "Nie mogę pobrać $name. Pobierz ręcznie z https://f-droid.org"
            warn "Szukaj: ${name//-/ } na f-droid.org"
        }
    else
        log "$name już pobrany: $APK_FILE"
    fi
done

# Instaluj
for name in termux termux-api termux-boot; do
    APK_FILE="${APK_DIR}/${name}.apk"
    if [[ -f "$APK_FILE" ]]; then
        log "Instaluję $name..."
        adb -s "$DEVICE" install -r -g "$APK_FILE" && log "$name ✓" || warn "$name — błąd instalacji"
    fi
done

# Uprawnienia Termux:API (SMS, kamera, lokalizacja, mikrofon)
log "Nadaję uprawnienia Termux:API..."
PERMS=(
    android.permission.READ_SMS
    android.permission.SEND_SMS
    android.permission.RECEIVE_SMS
    android.permission.CAMERA
    android.permission.ACCESS_FINE_LOCATION
    android.permission.ACCESS_COARSE_LOCATION
    android.permission.RECORD_AUDIO
    android.permission.READ_CONTACTS
    android.permission.READ_CALL_LOG
    android.permission.PROCESS_OUTGOING_CALLS
)
for perm in "${PERMS[@]}"; do
    adb -s "$DEVICE" shell pm grant com.termux.api "$perm" 2>/dev/null && \
        echo "  ✓ $perm" || echo "  ✗ $perm (może wymagać root lub Android < 14)"
done

# Push i uruchom setup script w Termux
log "Uruchamiam setup środowiska w Termux..."
SETUP="${SCRIPT_DIR}/setup_env.sh"
adb -s "$DEVICE" push "$SETUP" /sdcard/termux_setup.sh

# Uruchom przez Termux (via am)
adb -s "$DEVICE" shell "am start-activity \
    --user 0 \
    -n com.termux/.app.TermuxActivity \
    --es com.termux.app.extra.RUN_COMMAND_PATH '/data/data/com.termux/files/usr/bin/bash' \
    --esa com.termux.app.extra.RUN_COMMAND_ARGUMENTS '-l,/sdcard/termux_setup.sh' \
    --ez com.termux.app.extra.RUN_COMMAND_BACKGROUND false" 2>/dev/null || true

echo ""
log "Termux zainstalowany. Otwórz aplikację Termux ręcznie i poczekaj na setup."
echo "  Lub: adb shell am start -n com.termux/.app.TermuxActivity"
echo ""
echo "  Następny krok: bash scripts/termux/setup_ssh.sh"
