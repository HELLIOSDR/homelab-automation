#!/usr/bin/env bash
# adb_utils.sh — funkcje pomocnicze ADB (sourcuj w innych skryptach)

ADB_PORT=5555

# Połącz się z urządzeniem (USB lub IP)
adb_connect() {
    local target="${1:-}"
    if [[ -n "$target" ]]; then
        adb connect "$target:$ADB_PORT"
    else
        adb devices | grep -v "List of devices" | grep "device$" | awk '{print $1}' | head -1
    fi
}

# Włącz ADB przez WiFi (wywołaj gdy USB podłączone)
adb_enable_wifi() {
    local device="${1:-$(adb_connect)}"
    echo "[+] Włączam ADB TCP/IP na porcie $ADB_PORT..."
    adb -s "$device" tcpip $ADB_PORT
    sleep 2
    local ip
    ip=$(adb -s "$device" shell ip route | grep 'src' | awk '{print $NF}' | head -1 | tr -d '\r')
    echo "[+] IP urządzenia: $ip"
    echo "[+] Połącz się: adb connect $ip:$ADB_PORT"
    echo "$ip"
}

# Push i instaluj APK
adb_install_apk() {
    local device="$1"
    local apk="$2"
    echo "[+] Instaluję: $(basename "$apk")"
    adb -s "$device" install -r -g "$apk"
}

# Push plik na urządzenie
adb_push() {
    local device="$1"; local src="$2"; local dst="$3"
    adb -s "$device" push "$src" "$dst"
}

# Uruchom komendę w Termux (jeśli zainstalowany)
termux_run() {
    local device="$1"; shift
    adb -s "$device" shell "run-as com.termux files/usr/bin/bash -c '$*'" 2>/dev/null || \
    adb -s "$device" shell "am start -n com.termux/.app.TermuxActivity --es extra_arguments '$*'" 2>/dev/null
}

# Sprawdź czy Termux zainstalowany
has_termux() {
    local device="$1"
    adb -s "$device" shell pm list packages 2>/dev/null | grep -q "com.termux"
}

# Ustaw bezpieczne uprawnienia
grant_permissions() {
    local device="$1"
    local pkg="$2"
    shift 2
    for perm in "$@"; do
        adb -s "$device" shell pm grant "$pkg" "$perm" 2>/dev/null && \
            echo "[+] $pkg: $perm ✓" || \
            echo "[!] $pkg: $perm (brak dostępu)"
    done
}
