#!/usr/bin/env bash
# setup_ssh.sh — Konfiguruje SSH w Termux i reverse tunnel do homelab
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${SCRIPT_DIR}/../../config"
SSH_DIR="${CONFIG_DIR}/ssh"
mkdir -p "$SSH_DIR"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${GREEN}[+]${NC} $*"; }
info() { echo -e "${BLUE}[i]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
die()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }

DEVICE=$(adb devices | grep -v "List of devices" | grep "device$" | awk '{print $1}' | head -1)
[[ -z "$DEVICE" ]] && die "Brak urządzenia ADB"

PHONE_IP=$(adb -s "$DEVICE" shell "ip route | grep 'src' | awk '{print \$NF}' | head -1" | tr -d '\r\n')
log "IP telefonu: $PHONE_IP"

# Wygeneruj klucz SSH dla homelab → telefon
SSH_KEY="${SSH_DIR}/homelab_to_phone"
if [[ ! -f "$SSH_KEY" ]]; then
    log "Generuję klucz SSH..."
    ssh-keygen -t ed25519 -f "$SSH_KEY" -N "" -C "homelab-to-phone-$(date +%Y%m%d)"
fi
PUB_KEY=$(cat "${SSH_KEY}.pub")
log "Klucz publiczny: ${SSH_KEY}.pub"

# Wgraj klucz do Termux authorized_keys
log "Konfiguruję authorized_keys w Termux..."
adb -s "$DEVICE" shell "
    mkdir -p /data/data/com.termux/files/home/.ssh
    chmod 700 /data/data/com.termux/files/home/.ssh
    echo '${PUB_KEY}' >> /data/data/com.termux/files/home/.ssh/authorized_keys
    chmod 600 /data/data/com.termux/files/home/.ssh/authorized_keys
" 2>/dev/null || warn "Nie można ustawić przez ADB — zrób ręcznie w Termux"

# Uruchom sshd w Termux przez ADB
log "Uruchamiam SSH w Termux..."
adb -s "$DEVICE" shell "
    am start -n com.termux/.app.TermuxActivity 2>/dev/null
    sleep 2
" &>/dev/null || true

sleep 3

# Wyślij komendę start sshd
adb -s "$DEVICE" shell "
    export PATH=/data/data/com.termux/files/usr/bin:\$PATH
    /data/data/com.termux/files/usr/bin/sshd 2>/dev/null || true
" &>/dev/null || true

# Skonfiguruj reverse tunnel
echo ""
info "Konfiguracja reverse tunnel (opcjonalne, ale zalecane):"
echo "  Reverse tunnel pozwala łączyć się z telefonem przez 4G/5G,"
echo "  nawet gdy jest poza domową siecią."
echo ""
read -rp "  Adres homelab servera (np. 192.168.1.100 lub my.homelab.com): " HOMELAB_HOST
read -rp "  User SSH na homelab (np. pi, ubuntu): " HOMELAB_USER
read -rp "  Port tunnelu (np. 9022): " TUNNEL_PORT

# Konfiguracja tunnelu na telefonie
TUNNEL_CONFIG="HOMELAB_HOST=${HOMELAB_HOST}
HOMELAB_USER=${HOMELAB_USER}
TUNNEL_PORT=${TUNNEL_PORT}"

adb -s "$DEVICE" shell "
    mkdir -p /data/data/com.termux/files/home/.config
    echo '${TUNNEL_CONFIG}' > /data/data/com.termux/files/home/.config/homelab_tunnel.env
" 2>/dev/null || warn "Zapisz ręcznie w Termux"

# Wygeneruj klucz dla odwrotnego połączenia (telefon → homelab)
PHONE_KEY="${SSH_DIR}/phone_to_homelab"
if [[ ! -f "$PHONE_KEY" ]]; then
    ssh-keygen -t ed25519 -f "$PHONE_KEY" -N "" -C "phone-to-homelab"
fi
PHONE_PUB=$(cat "${PHONE_KEY}.pub")

echo ""
log "KONFIGURACJA ZAKOŃCZONA"
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  DOSTĘP DO TELEFONU"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "  Przez WiFi (lokalna sieć):"
echo "    ssh -p 8022 -i $SSH_KEY u0_a$(date +%N | cut -c1-3)@$PHONE_IP"
echo ""
echo "  Przez reverse tunnel (z dowolnego miejsca):"
echo "    ssh -p $TUNNEL_PORT localhost  # na serwerze $HOMELAB_HOST"
echo ""
echo "  ADB WiFi:"
echo "    adb connect $PHONE_IP:5555"
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  DODAJ TEN KLUCZ DO ~/.ssh/authorized_keys NA HOMELABSIE:"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "  $PHONE_PUB"
echo ""

# Zapisz connection info
cat > "${CONFIG_DIR}/connection_info.json" << JSON
{
  "phone_ip": "$PHONE_IP",
  "ssh_port": 8022,
  "adb_tcp_port": 5555,
  "ssh_key": "$SSH_KEY",
  "tunnel": {
    "homelab_host": "$HOMELAB_HOST",
    "homelab_user": "$HOMELAB_USER",
    "tunnel_port": $TUNNEL_PORT
  },
  "connect_commands": {
    "local_ssh": "ssh -p 8022 -i $SSH_KEY -o StrictHostKeyChecking=no u0@$PHONE_IP",
    "via_tunnel": "ssh -p $TUNNEL_PORT localhost",
    "adb_wifi": "adb connect $PHONE_IP:5555"
  }
}
JSON
log "Zapisano: ${CONFIG_DIR}/connection_info.json"
