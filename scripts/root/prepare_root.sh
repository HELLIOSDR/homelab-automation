#!/usr/bin/env bash
# prepare_root.sh — Przygotowanie root Samsung A23 5G przez Heimdall + Magisk
# Uruchom po sprawdzeniu check_device.sh i włączeniu OEM unlock
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE="${SCRIPT_DIR}/../../config/device_profile.json"
WORK_DIR="${SCRIPT_DIR}/../../.root_work"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${GREEN}[+]${NC} $*"; }
info() { echo -e "${BLUE}[i]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
die()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }

# Załaduj profil urządzenia
if [[ ! -f "$PROFILE" ]]; then
    die "Profil nie znaleziony. Uruchom najpierw: bash scripts/adb/check_device.sh"
fi

MODEL=$(python3 -c "import json,sys; d=json.load(open('$PROFILE')); print(d.get('model','unknown'))" 2>/dev/null || echo "unknown")
DEVICE_CODE=$(python3 -c "import json,sys; d=json.load(open('$PROFILE')); print(d.get('device_code','unknown'))" 2>/dev/null || echo "unknown")
ANDROID=$(python3 -c "import json,sys; d=json.load(open('$PROFILE')); print(d.get('android_version','0'))" 2>/dev/null || echo "0")
BOOT_STATE=$(python3 -c "import json,sys; d=json.load(open('$PROFILE')); print(d.get('boot_state','unknown'))" 2>/dev/null || echo "unknown")

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  ROOT PREP: $MODEL ($DEVICE_CODE) — Android $ANDROID"
echo "═══════════════════════════════════════════════════════"

# Sprawdź czy OEM unlock włączony
if [[ "$BOOT_STATE" == "green" ]]; then
    echo ""
    warn "BOOTLOADER JEST ZABLOKOWANY!"
    echo ""
    echo "  WYMAGANE (wykonaj ręcznie na telefonie):"
    echo "  1. Ustawienia → O telefonie → 'Numer kompilacji' (kliknij 7x)"
    echo "  2. Ustawienia → Opcje programistyczne → OEM Unlocking → WŁĄCZ"
    echo "  3. Restart telefonu"
    echo "  4. Uruchom ten skrypt ponownie"
    echo ""
    exit 1
fi

# Sprawdź heimdall
if ! command -v heimdall &>/dev/null; then
    log "Instaluję heimdall..."
    if command -v apt &>/dev/null; then
        apt-get install -y heimdall-flash 2>/dev/null || \
        (apt-get install -y build-essential libusb-1.0-0-dev cmake libgl1-mesa-dev && \
         git clone https://github.com/Benjamin-Dobell/Heimdall /tmp/heimdall && \
         cd /tmp/heimdall && cmake -DCMAKE_BUILD_TYPE=Release . && make && \
         cp bin/heimdall /usr/local/bin/)
    fi
fi
command -v heimdall &>/dev/null || die "Heimdall niedostępny"

mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

# Pobierz Magisk APK
MAGISK_VER="v27.0"
MAGISK_APK="${WORK_DIR}/Magisk-${MAGISK_VER}.apk"
if [[ ! -f "$MAGISK_APK" ]]; then
    log "Pobieram Magisk $MAGISK_VER..."
    curl -L "https://github.com/topjohnwu/Magisk/releases/download/${MAGISK_VER}/Magisk-${MAGISK_VER}.apk" \
         -o "$MAGISK_APK"
fi

# Wykryj wariant modelu dla firmware
detect_firmware_variant() {
    case "$DEVICE_CODE" in
        a23xq)   echo "SM-A236B" ;; # International
        a23x)    echo "SM-A236U" ;; # US
        a23xq_n) echo "SM-A236N" ;; # Korea
        *)
            # Zapytaj użytkownika
            echo ""
            warn "Nie mogę auto-wykryć wariantu. Podaj model:"
            echo "  1) SM-A236B (International/EU)"
            echo "  2) SM-A236U (USA)"
            echo "  3) SM-A236N (Korea)"
            read -rp "  Wybierz [1-3]: " choice
            case "$choice" in
                1) echo "SM-A236B" ;;
                2) echo "SM-A236U" ;;
                3) echo "SM-A236N" ;;
                *) echo "SM-A236B" ;;
            esac
            ;;
    esac
}

VARIANT=$(detect_firmware_variant)
log "Wariant modelu: $VARIANT"

echo ""
info "Następne kroki (częściowo ręczne):"
echo ""
echo "  KROK 1 — Zainstaluj Magisk APK na telefonie:"
echo "    adb install -g $MAGISK_APK"
echo ""
echo "  KROK 2 — Pobierz stock firmware dla $VARIANT Android $ANDROID:"
echo "    https://samfw.com lub https://samfrew.com"
echo "    Szukaj: $VARIANT"
echo ""
echo "  KROK 3 — Wypakuj boot.img z firmware i patchuj w Magisk:"
echo "    Na telefonie: Magisk → Install → Select and Patch a File → wybierz boot.img"
echo "    Skopiuj spatchowany plik na PC:"
echo "    adb pull /sdcard/Download/magisk_patched_*.img $WORK_DIR/magisk_patched_boot.img"
echo ""
echo "  KROK 4 — Flash spatchowanego boot.img:"
echo "    bash scripts/root/flash_magisk.sh"
echo ""

# Zainstaluj Magisk APK od razu
DEVICE=$(adb devices | grep -v "List of devices" | grep "device$" | awk '{print $1}' | head -1)
if [[ -n "$DEVICE" ]]; then
    log "Instaluję Magisk APK na urządzeniu $DEVICE..."
    adb -s "$DEVICE" install -r -g "$MAGISK_APK" && \
        log "Magisk zainstalowany. Otwórz na telefonie i patchuj boot.img." || \
        warn "Instalacja nie powiodła się — zainstaluj ręcznie."
fi

echo ""
log "Praca w: $WORK_DIR"
