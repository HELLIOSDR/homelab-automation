#!/usr/bin/env bash
# check_device.sh — wykrywa A23 5G przez ADB i generuje device_profile.json
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT="${SCRIPT_DIR}/../../config/device_profile.json"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
die()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }

command -v adb &>/dev/null || die "adb nie znaleziony. Zainstaluj: apt install android-tools-adb"

log "Szukam podłączonych urządzeń..."
DEVICES=$(adb devices | grep -v "List of devices" | grep "device$" | awk '{print $1}')

if [[ -z "$DEVICES" ]]; then
    echo ""
    warn "Brak autoryzowanych urządzeń ADB!"
    echo ""
    echo "  1. Upewnij się że USB debugging jest włączone:"
    echo "     Ustawienia → O telefonie → kliknij 7x 'Numer kompilacji'"
    echo "     Ustawienia → Opcje programistyczne → Debugowanie USB ✓"
    echo ""
    echo "  2. Na telefonie: zatwierdź okno 'Zezwól na debugowanie USB'"
    echo "  3. Uruchom ponownie: bash $0"
    exit 1
fi

DEVICE=$(echo "$DEVICES" | head -1)
log "Urządzenie: $DEVICE"

adb_get() { adb -s "$DEVICE" shell getprop "$1" 2>/dev/null | tr -d '\r\n'; }
adb_run() { adb -s "$DEVICE" shell "$@" 2>/dev/null | tr -d '\r'; }

MODEL=$(adb_get ro.product.model)
BRAND=$(adb_get ro.product.brand)
DEVICE_CODE=$(adb_get ro.product.device)
ANDROID_VER=$(adb_get ro.build.version.release)
SDK=$(adb_get ro.build.version.sdk)
BUILD=$(adb_get ro.build.display.id)
BOOTLOADER=$(adb_get ro.bootloader)
BOOT_STATE=$(adb_get ro.boot.verifiedbootstate)
OEM_UNLOCK=$(adb_get ro.oem_unlock_supported)
SECURE=$(adb_get ro.secure)
DEBUGGABLE=$(adb_get ro.debuggable)
SERIAL=$(adb_get ro.serialno)
ARCH=$(adb_get ro.product.cpu.abi)
RAM_KB=$(adb_run "cat /proc/meminfo | grep MemTotal | awk '{print \$2}'")
RAM_GB=$(echo "scale=1; $RAM_KB / 1048576" | bc 2>/dev/null || echo "?")
BATTERY=$(adb_run "dumpsys battery | grep level | awk '{print \$2}'")
IP=$(adb_run "ip route | grep 'src' | awk '{print \$NF}' | head -1")

echo ""
echo "═══════════════════════════════════════════════"
echo "  DEVICE PROFILE: $BRAND $MODEL"
echo "═══════════════════════════════════════════════"
printf "  Model:        %s\n" "$MODEL"
printf "  Device code:  %s\n" "$DEVICE_CODE"
printf "  Android:      %s (SDK %s)\n" "$ANDROID_VER" "$SDK"
printf "  Build:        %s\n" "$BUILD"
printf "  Bootloader:   %s\n" "$BOOTLOADER"
printf "  Boot state:   %s\n" "$BOOT_STATE"
printf "  OEM unlock:   %s\n" "$OEM_UNLOCK"
printf "  Secure:       %s\n" "$SECURE"
printf "  Architecture: %s\n" "$ARCH"
printf "  RAM:          %s GB\n" "$RAM_GB"
printf "  Battery:      %s%%\n" "$BATTERY"
printf "  IP (LAN):     %s\n" "$IP"
echo "═══════════════════════════════════════════════"

# Root check
ROOT_STATUS="no"
if adb -s "$DEVICE" shell su -c 'echo rooted' 2>/dev/null | grep -q rooted; then
    ROOT_STATUS="yes"
    log "ROOT: Aktywny!"
else
    warn "ROOT: Brak (wymagany dla pełnej autonomii)"
fi

# Zapisz profil JSON
mkdir -p "$(dirname "$OUTPUT")"
cat > "$OUTPUT" <<JSON
{
  "serial": "$SERIAL",
  "model": "$MODEL",
  "brand": "$BRAND",
  "device_code": "$DEVICE_CODE",
  "android_version": "$ANDROID_VER",
  "sdk": $SDK,
  "build": "$BUILD",
  "bootloader": "$BOOTLOADER",
  "boot_state": "$BOOT_STATE",
  "oem_unlock_supported": "$OEM_UNLOCK",
  "secure": "$SECURE",
  "architecture": "$ARCH",
  "ram_gb": "$RAM_GB",
  "battery_percent": "$BATTERY",
  "ip_lan": "$IP",
  "root": "$ROOT_STATUS",
  "adb_serial": "$DEVICE",
  "checked_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
JSON

log "Profil zapisany: $OUTPUT"

# Rekomendacje
echo ""
if [[ "$BOOT_STATE" == "orange" ]] || [[ "$OEM_UNLOCK" == "1" ]]; then
    warn "OEM unlock jest włączony/obsługiwany — gotowe do root"
elif [[ "$BOOT_STATE" == "green" ]]; then
    warn "Bootloader LOCKED — przed rootem włącz OEM unlock w ustawieniach"
fi

if [[ "$ROOT_STATUS" == "no" ]]; then
    echo ""
    echo "  Następny krok: bash scripts/root/prepare_root.sh"
fi
echo ""
