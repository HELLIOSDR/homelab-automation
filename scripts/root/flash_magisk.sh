#!/usr/bin/env bash
# flash_magisk.sh — Flash spatchowanego boot.img przez Heimdall (Download Mode)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="${SCRIPT_DIR}/../../.root_work"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
die()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }

PATCHED_BOOT=$(ls "$WORK_DIR"/magisk_patched_*.img 2>/dev/null | head -1 || echo "")

if [[ -z "$PATCHED_BOOT" ]]; then
    die "Nie znaleziono magisk_patched_*.img w $WORK_DIR\nWykonaj najpierw kroki z prepare_root.sh"
fi

log "Znaleziono spatchowany boot: $PATCHED_BOOT"

echo ""
echo "  ⚠️  WCHODZENIE W TRYB DOWNLOAD MODE"
echo "  ─────────────────────────────────────────────────────"
echo "  1. Wyłącz telefon całkowicie"
echo "  2. Przytrzymaj VOL DOWN + podłącz kabel USB"
echo "  3. Na ekranie pojawi się 'Downloading...'"
echo "  4. Wciśnij ENTER tutaj gdy gotowe"
echo ""
read -rp "  [ENTER gdy telefon w Download Mode] "

# Sprawdź czy heimdall widzi urządzenie
log "Sprawdzam połączenie Heimdall..."
if ! heimdall detect &>/dev/null; then
    die "Heimdall nie widzi urządzenia w Download Mode.\nSprawdź udev rules: echo 'SUBSYSTEM==\"usb\", ATTRS{idVendor}==\"04e8\", MODE=\"0666\"' > /etc/udev/rules.d/51-samsung.rules && udevadm control --reload-rules"
fi

log "Urządzenie wykryte. Flashuję boot partition..."
heimdall flash --BOOT "$PATCHED_BOOT" --no-reboot

log "Flash zakończony!"
echo ""
echo "  Telefon uruchomi się automatycznie."
echo "  Przy pierwszym starcie z Magiskiem:"
echo "    - może być wolniejszy boot (normalnie)"
echo "    - otwórz Magisk i kliknij 'OK' dla dodatkowego kroku"
echo ""
echo "  Po restart: bash scripts/root/verify_root.sh"
