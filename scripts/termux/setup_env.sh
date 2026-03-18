#!/data/data/com.termux/files/usr/bin/bash
# setup_env.sh — Uruchom WEWNĄTRZ Termux na telefonie
# Instaluje Python, pip, git, SSH i wszystkie zależności AI agenta

set -euo pipefail

echo "[setup] Start: $(date)"

# Aktualizacja i podstawowe pakiety
pkg update -y && pkg upgrade -y

pkg install -y \
    python \
    python-pip \
    git \
    curl \
    wget \
    openssh \
    termux-api \
    jq \
    nano \
    htop \
    nmap \
    iproute2 \
    net-tools \
    socat \
    openssl \
    cronie

# Python packages dla AI agenta
pip install --upgrade pip

pip install \
    anthropic \
    fastapi \
    uvicorn \
    aiohttp \
    requests \
    pydantic \
    python-dotenv \
    schedule \
    psutil \
    Pillow \
    numpy

echo "[setup] Pakiety zainstalowane ✓"

# Utwórz strukturę katalogów agenta
mkdir -p \
    ~/ai_agent/sensors \
    ~/ai_agent/logs \
    ~/ai_agent/data/photos \
    ~/ai_agent/data/audio \
    ~/ai_agent/config

# Skopiuj agenta z /sdcard jeśli istnieje
if ls /sdcard/ai_agent_*.tar.gz 2>/dev/null | head -1; then
    ARCHIVE=$(ls /sdcard/ai_agent_*.tar.gz | sort -r | head -1)
    echo "[setup] Rozpakowuję agenta z $ARCHIVE..."
    tar -xzf "$ARCHIVE" -C ~/
fi

# Autostart Termux:Boot
mkdir -p ~/.termux/boot
cat > ~/.termux/boot/start_agent.sh << 'BOOT'
#!/data/data/com.termux/files/usr/bin/bash
# Autostart przy każdym uruchomieniu Android

# SSH server
sshd

# Reverse tunnel do homelab (jeśli skonfigurowany)
if [[ -f ~/.config/homelab_tunnel.env ]]; then
    source ~/.config/homelab_tunnel.env
    while true; do
        ssh -o StrictHostKeyChecking=no \
            -o ServerAliveInterval=30 \
            -o ExitOnForwardFailure=yes \
            -N -R "${TUNNEL_PORT}:localhost:8022" \
            "${HOMELAB_USER}@${HOMELAB_HOST}" \
            -i ~/.ssh/homelab_key 2>/dev/null || true
        sleep 30
    done &
fi

# AI Agent
if [[ -f ~/ai_agent/brain.py ]]; then
    cd ~/ai_agent
    source .env 2>/dev/null || true
    python brain.py >> logs/agent.log 2>&1 &
fi
BOOT
chmod +x ~/.termux/boot/start_agent.sh

echo "[setup] Autostart skonfigurowany ✓"
echo "[setup] Uruchom: bash scripts/termux/setup_ssh.sh (na PC)"
echo "[setup] Gotowe: $(date)"
