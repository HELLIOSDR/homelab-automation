#!/usr/bin/env bash
# verify_root.sh — Weryfikuje root i aktualizuje device_profile.json
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE="${SCRIPT_DIR}/../../config/device_profile.json"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
die()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }

DEVICE=$(adb devices | grep -v "List of devices" | grep "device$" | awk '{print $1}' | head -1)
[[ -z "$DEVICE" ]] && die "Brak urządzenia ADB"

log "Sprawdzam root na $DEVICE..."

# Test 1: su bezpośredni
if adb -s "$DEVICE" shell "su -c 'id'" 2>/dev/null | grep -q "uid=0"; then
    log "ROOT: ✓ su działa (uid=0)"
    ROOT="yes"
else
    warn "ROOT: su nie odpowiada"
    ROOT="no"
fi

# Test 2: Magisk
if adb -s "$DEVICE" shell "magisk -v" 2>/dev/null | grep -q "Magisk"; then
    MAGISK_VER=$(adb -s "$DEVICE" shell "magisk -v" 2>/dev/null | tr -d '\r')
    log "MAGISK: ✓ $MAGISK_VER"
else
    warn "MAGISK: nie znaleziony w PATH"
fi

# Test 3: /system/xbin/su
if adb -s "$DEVICE" shell "ls /system/xbin/su" 2>/dev/null | grep -q "su"; then
    log "su binary: ✓ /system/xbin/su"
fi

# Zapisz wynik do profilu
if [[ -f "$PROFILE" ]]; then
    python3 - <<EOF
import json
with open("$PROFILE") as f:
    d = json.load(f)
d["root"] = "$ROOT"
d["root_verified_at"] = "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
with open("$PROFILE", "w") as f:
    json.dump(d, f, indent=2)
print("Profil zaktualizowany.")
EOF
fi

if [[ "$ROOT" == "yes" ]]; then
    echo ""
    log "SUKCES! Urządzenie jest zrootowane."
    echo "  Następny krok: bash scripts/termux/install_termux.sh"
else
    echo ""
    warn "Root nie aktywny. Sprawdź:"
    echo "  1. Czy Magisk był zainstalowany poprawnie?"
    echo "  2. Czy wykonałeś dodatkowy krok inicjalizacji Magisk po pierwszym restart?"
    echo "  3. Spróbuj: adb shell su -c id"
fi
