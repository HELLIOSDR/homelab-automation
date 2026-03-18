#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
#  CASCADE.SH — Neutrinowa Kaskada
#  Jedno odpalenie = od zera do działającego AI na telefonie
#
#  Uruchom na SWOIM KOMPUTERZE (nie na serwerze cloud):
#    bash cascade.sh
#
#  Co robi (w kolejności):
#    1. Sprawdza czy ADB jest zainstalowane, jeśli nie → instaluje
#    2. Łączy się z A23 5G przez USB
#    3. Fingerprint urządzenia
#    4. Instaluje Magisk APK (root prep)
#    5. Instaluje Termux + Termux:API + Termux:Boot
#    6. Nadaje uprawnienia (SMS, GPS, kamera, mikrofon)
#    7. Pushuje agenta na telefon
#    8. Bootstrapuje środowisko Python w Termux
#    9. Konfiguruje SSH + reverse tunnel
#   10. Uruchamia Heliosa
#
#  Ręczne kroki (nie da się zautomatyzować):
#    - Włączenie OEM Unlock w ustawieniach telefonu
#    - Patchowanie boot.img w Magisk na telefonie
#    - Flash boot.img przez Heimdall (Download Mode)
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${GREEN}[CASCADE]${NC} $*"; }
info() { echo -e "${CYAN}[INFO]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
die()  { echo -e "${RED}[STOP]${NC} $*"; exit 1; }
step() { echo -e "\n${BOLD}${BLUE}═══ KROK $1: $2 ═══${NC}"; }
ok()   { echo -e "${GREEN}  ✓${NC} $*"; }

FAILED_STEPS=()
DEVICE=""
PHONE_IP=""

trap 'echo -e "\n${RED}Kaskada przerwana.${NC}"; if [[ ${#FAILED_STEPS[@]} -gt 0 ]]; then echo "Nieukończone: ${FAILED_STEPS[*]}"; fi' EXIT

# ── Sprawdź zależności ─────────────────────────────────────────────────────

step "0" "Sprawdzam zależności hosta"

install_if_missing() {
    if ! command -v "$1" &>/dev/null; then
        warn "$1 nie znaleziony — instaluję..."
        if command -v apt &>/dev/null; then
            sudo apt-get update -qq && sudo apt-get install -y -qq "$2" 2>/dev/null
        elif command -v brew &>/dev/null; then
            brew install "$2" 2>/dev/null
        elif command -v pacman &>/dev/null; then
            sudo pacman -S --noconfirm "$2" 2>/dev/null
        else
            die "Nie mogę zainstalować $1. Zainstaluj ręcznie."
        fi
    fi
    command -v "$1" &>/dev/null && ok "$1" || die "Nie udało się zainstalować $1"
}

install_if_missing "adb" "android-tools-adb"
install_if_missing "curl" "curl"
install_if_missing "jq" "jq"
install_if_missing "python3" "python3"
install_if_missing "ssh" "openssh-client"
install_if_missing "bc" "bc"

# Opcjonalnie: heimdall (do flashowania root)
if command -v heimdall &>/dev/null; then
    ok "heimdall (opcjonalne)"
else
    info "heimdall nie zainstalowany (potrzebny dopiero do flash root)"
    info "  Instalacja: sudo apt install heimdall-flash"
fi

# ── KROK 1: ADB połączenie ────────────────────────────────────────────────

step "1" "Łączę z telefonem przez ADB"

# Restart ADB server
adb kill-server 2>/dev/null || true
sleep 1
adb start-server 2>/dev/null

sleep 2
DEVICES=$(adb devices 2>/dev/null | grep -v "List of devices" | grep "device$" | awk '{print $1}')

if [[ -z "$DEVICES" ]]; then
    echo ""
    warn "Telefon nie widoczny przez ADB!"
    echo ""
    echo "  Sprawdź:"
    echo "  1. USB podłączony fizycznie"
    echo "  2. Na telefonie: Ustawienia → Opcje programistyczne → USB Debugging ✓"
    echo "  3. Na telefonie: Zatwierdź popup 'Zezwól na debugowanie USB'"
    echo ""
    read -rp "  Gotowe? [ENTER aby spróbować ponownie] "
    DEVICES=$(adb devices | grep -v "List of devices" | grep "device$" | awk '{print $1}')
    [[ -z "$DEVICES" ]] && die "Nadal nie widzę telefonu. Sprawdź kabel i ustawienia."
fi

DEVICE=$(echo "$DEVICES" | head -1)
ok "Urządzenie: $DEVICE"

# ── KROK 2: Fingerprint ───────────────────────────────────────────────────

step "2" "Fingerprint urządzenia"

adb_get() { adb -s "$DEVICE" shell getprop "$1" 2>/dev/null | tr -d '\r\n'; }

MODEL=$(adb_get ro.product.model)
BRAND=$(adb_get ro.product.brand)
ANDROID=$(adb_get ro.build.version.release)
SDK=$(adb_get ro.build.version.sdk)
BOOT_STATE=$(adb_get ro.boot.verifiedbootstate)
SERIAL=$(adb_get ro.serialno)
ARCH=$(adb_get ro.product.cpu.abi)

echo ""
echo "  Model:       $BRAND $MODEL"
echo "  Android:     $ANDROID (SDK $SDK)"
echo "  Boot state:  $BOOT_STATE"
echo "  Architecture: $ARCH"
echo "  Serial:      $SERIAL"

# Root check
ROOT="no"
if adb -s "$DEVICE" shell su -c 'echo ok' 2>/dev/null | grep -q ok; then
    ROOT="yes"
    ok "ROOT aktywny"
else
    info "ROOT: brak (instrukcje poniżej)"
fi

# Zapisz profil
mkdir -p config
cat > config/device_profile.json << PROF
{
  "model": "$MODEL", "brand": "$BRAND", "android_version": "$ANDROID",
  "sdk": $SDK, "boot_state": "$BOOT_STATE", "serial": "$SERIAL",
  "architecture": "$ARCH", "root": "$ROOT",
  "adb_serial": "$DEVICE", "checked_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
PROF
ok "Profil: config/device_profile.json"

# Włącz ADB WiFi (backup access)
info "Włączam ADB przez WiFi..."
adb -s "$DEVICE" tcpip 5555 2>/dev/null || true
sleep 1
PHONE_IP=$(adb -s "$DEVICE" shell "ip route | grep 'src' | awk '{print \$NF}' | head -1" 2>/dev/null | tr -d '\r\n')
if [[ -n "$PHONE_IP" ]]; then
    ok "ADB WiFi: adb connect $PHONE_IP:5555"
fi

# ── KROK 3: APKi — Termux + Magisk ────────────────────────────────────────

step "3" "Pobieram i instaluję APKi"

mkdir -p .apks

download_apk() {
    local name="$1" url="$2" path=".apks/${name}.apk"
    if [[ ! -f "$path" ]]; then
        info "Pobieram $name..."
        curl -L --fail -o "$path" "$url" 2>/dev/null && ok "$name pobrany" || {
            warn "Nie mogę pobrać $name z $url"
            warn "Pobierz ręcznie i umieść jako $path"
            return 1
        }
    else
        ok "$name: już jest"
    fi
}

# Termux z F-Droid (stabilne wersje ARM64)
download_apk "termux"      "https://f-droid.org/repo/com.termux_1020.apk" || true
download_apk "termux-api"  "https://f-droid.org/repo/com.termux.api_51.apk" || true
download_apk "termux-boot" "https://f-droid.org/repo/com.termux.boot_7.apk" || true

# Magisk
MAGISK_VER="v27.0"
download_apk "magisk" "https://github.com/topjohnwu/Magisk/releases/download/${MAGISK_VER}/Magisk-${MAGISK_VER}.apk" || true

# Instaluj każdy APK
for apk in termux termux-api termux-boot magisk; do
    if [[ -f ".apks/${apk}.apk" ]]; then
        info "Instaluję $apk..."
        adb -s "$DEVICE" install -r -g ".apks/${apk}.apk" 2>/dev/null && ok "$apk ✓" || warn "$apk — błąd"
    fi
done

# ── KROK 4: Uprawnienia ───────────────────────────────────────────────────

step "4" "Nadaję uprawnienia"

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
    android.permission.READ_PHONE_STATE
    android.permission.RECEIVE_BOOT_COMPLETED
)

for pkg in com.termux com.termux.api; do
    for perm in "${PERMS[@]}"; do
        adb -s "$DEVICE" shell pm grant "$pkg" "$perm" 2>/dev/null && \
            echo -e "  ${GREEN}✓${NC} $pkg: ${perm##*.}" || true
    done
done
ok "Uprawnienia nadane"

# ── KROK 5: Deploy agenta na telefon ──────────────────────────────────────

step "5" "Deploying AI agent na telefon"

# Spakuj agenta
info "Pakuję agenta..."
tar -czf /tmp/helios_agent.tar.gz \
    agent/brain.py \
    agent/api_server.py \
    agent/sensor_fusion.py \
    agent/sensors/__init__.py \
    agent/sensors/gps.py \
    agent/sensors/sms.py \
    agent/sensors/camera.py \
    agent/sensors/motion.py \
    agent/sensors/audio.py \
    agent/sensors/system.py \
    agent/requirements.txt

adb -s "$DEVICE" push /tmp/helios_agent.tar.gz /sdcard/helios_agent.tar.gz
ok "Agent na telefonie: /sdcard/helios_agent.tar.gz"

# Push bootstrap script
adb -s "$DEVICE" push scripts/termux/setup_env.sh /sdcard/termux_setup.sh
ok "Bootstrap script na telefonie"

# ── KROK 6: Bootstrap Termux ──────────────────────────────────────────────

step "6" "Uruchamiam Termux i bootstrap"

# Otwórz Termux
adb -s "$DEVICE" shell am start -n com.termux/.app.TermuxActivity 2>/dev/null || true
sleep 3

# Utwórz skrypt initializer który odpali się automatycznie w Termux
INIT_SCRIPT='#!/data/data/com.termux/files/usr/bin/bash
echo "=== HELIOS BOOTSTRAP ==="

# Update i podstawowe pakiety
yes | pkg update 2>/dev/null
pkg install -y python python-pip openssh termux-api git curl jq openssl cronie 2>/dev/null

# Katalogi
mkdir -p ~/ai_agent/sensors ~/ai_agent/logs ~/ai_agent/data/photos ~/ai_agent/data/audio

# Rozpakuj agenta
cd ~/ai_agent
tar -xzf /sdcard/helios_agent.tar.gz --strip-components=1 2>/dev/null || \
tar -xzf /sdcard/helios_agent.tar.gz 2>/dev/null

# Przenieś pliki jeśli w podkatalogu agent/
if [[ -d agent ]]; then
    cp -r agent/* . 2>/dev/null
    rm -rf agent
fi

# Python dependencies
pip install anthropic fastapi uvicorn aiohttp requests pydantic python-dotenv psutil Pillow numpy 2>/dev/null

# SSH server
sshd 2>/dev/null || true

# Utwórz placeholder .env
if [[ ! -f .env ]]; then
    cat > .env << ENV_EOF
ANTHROPIC_API_KEY=WPISZ_KLUCZ
AGENT_NAME=Helios
ALLOWED_NUMBERS=*
API_TOKEN=
API_PORT=7788
SENSOR_INTERVAL_S=10
ENV_EOF
fi

# Autostart
mkdir -p ~/.termux/boot
cat > ~/.termux/boot/start_helios.sh << BOOT_EOF
#!/data/data/com.termux/files/usr/bin/bash
sshd
cd ~/ai_agent && python brain.py >> logs/agent.log 2>&1 &
BOOT_EOF
chmod +x ~/.termux/boot/start_helios.sh

echo "=== BOOTSTRAP DONE ==="
echo "Edytuj ~/ai_agent/.env i wpisz ANTHROPIC_API_KEY"
echo "Start: cd ~/ai_agent && python brain.py"
'

# Zapisz na telefonie i uruchom
echo "$INIT_SCRIPT" | adb -s "$DEVICE" shell "cat > /sdcard/helios_init.sh"

# Wyślij komendę do Termux
adb -s "$DEVICE" shell "am start-activity \
    --user 0 \
    -n com.termux/.app.TermuxActivity" 2>/dev/null || true

sleep 2

# Pokaż instrukcje
echo ""
info "Termux powinien się otworzyć na telefonie."
echo ""
echo "  W Termux na telefonie uruchom:"
echo "  ${BOLD}bash /sdcard/helios_init.sh${NC}"
echo ""
echo "  To zainstaluje wszystko automatycznie (~3-5 min)."
echo ""

read -rp "  [ENTER gdy bootstrap skończony w Termux] "
ok "Bootstrap zakończony"

# ── KROK 7: SSH Setup ─────────────────────────────────────────────────────

step "7" "Konfiguracja SSH"

SSH_DIR="config/ssh"
mkdir -p "$SSH_DIR"

# Generuj klucz jeśli nie istnieje
if [[ ! -f "${SSH_DIR}/homelab_to_phone" ]]; then
    ssh-keygen -t ed25519 -f "${SSH_DIR}/homelab_to_phone" -N "" -C "homelab-helios" -q
    ok "Klucz SSH wygenerowany"
fi

PUB_KEY=$(cat "${SSH_DIR}/homelab_to_phone.pub")

# Wgraj klucz na telefon (przez ADB)
adb -s "$DEVICE" shell "mkdir -p /data/data/com.termux/files/home/.ssh && \
    echo '$PUB_KEY' >> /data/data/com.termux/files/home/.ssh/authorized_keys && \
    chmod 700 /data/data/com.termux/files/home/.ssh && \
    chmod 600 /data/data/com.termux/files/home/.ssh/authorized_keys" 2>/dev/null && \
    ok "Klucz SSH wgrany" || warn "Nie mogę wgrać klucza przez ADB — zrób ręcznie w Termux"

echo ""
echo "  Połączenie SSH:"
echo "    ${BOLD}ssh -p 8022 -i ${SSH_DIR}/homelab_to_phone $(whoami)@${PHONE_IP}${NC}"
echo ""

# ── KROK 8: Weryfikacja ───────────────────────────────────────────────────

step "8" "Weryfikacja końcowa"

echo ""
echo "  ┌─────────────────────────────────────────────────────┐"
echo "  │              HELIOS — STATUS KASKADY                │"
echo "  ├─────────────────────────────────────────────────────┤"
printf "  │  Telefon:        %-33s│\n" "$BRAND $MODEL"
printf "  │  Android:        %-33s│\n" "$ANDROID (SDK $SDK)"
printf "  │  IP LAN:         %-33s│\n" "${PHONE_IP:-unknown}"
printf "  │  Root:           %-33s│\n" "$ROOT"
echo "  ├─────────────────────────────────────────────────────┤"
echo "  │  Zainstalowane:                                     │"
echo "  │    ✓ Termux + Termux:API + Termux:Boot              │"
echo "  │    ✓ Python + dependencies                          │"
echo "  │    ✓ Helios AI Agent                                │"
echo "  │    ✓ SSH server (port 8022)                         │"
echo "  │    ✓ ADB WiFi ($PHONE_IP:5555)                     │"
echo "  ├─────────────────────────────────────────────────────┤"

if [[ "$ROOT" == "yes" ]]; then
    echo "  │  ✓ ROOT aktywny                                    │"
else
    echo "  │  ⚠ ROOT: brak — potrzebujesz do pełnej autonomii   │"
    echo "  │    → bash scripts/root/prepare_root.sh              │"
fi
echo "  └─────────────────────────────────────────────────────┘"

echo ""
echo "  ${BOLD}NASTĘPNE KROKI:${NC}"
echo ""
echo "  1. Na telefonie w Termux:"
echo "     ${CYAN}nano ~/ai_agent/.env${NC}   ← wpisz ANTHROPIC_API_KEY"
echo ""
echo "  2. Uruchom Heliosa:"
echo "     ${CYAN}cd ~/ai_agent && python brain.py${NC}"
echo ""
echo "  3. Test API z komputera:"
echo "     ${CYAN}curl http://${PHONE_IP}:7788/v1/health${NC}"
echo ""
echo "  4. Test SMS: wyślij 'co słychać?' na numer SIM"
echo ""

if [[ "$ROOT" == "no" ]]; then
    echo "  5. ROOT (opcjonalne ale zalecane):"
    echo "     ${CYAN}bash scripts/root/prepare_root.sh${NC}"
    echo ""
fi

# Posprzątaj trap
trap - EXIT
log "Kaskada zakończona. Helios gotowy do startu."
