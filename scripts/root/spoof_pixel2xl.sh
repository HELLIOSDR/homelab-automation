#!/usr/bin/env bash
# spoof_pixel2xl.sh — Podszywanie się pod Pixel 2 XL przez Magisk Props
# Przydatne gdy Google Play lub inne usługi są ograniczone dla A23 5G.
# WYMAGA root (Magisk) i zainstalowanego MagiskHide Props Config.
set -euo pipefail

DEVICE=$(adb devices | grep -v "List of devices" | grep "device$" | awk '{print $1}' | head -1)
[[ -z "$DEVICE" ]] && { echo "[!] Brak urządzenia ADB"; exit 1; }

echo "[+] Spoofowanie jako Google Pixel 2 XL (taimen)..."

# Pixel 2 XL build props
PROPS=(
    "ro.product.brand=google"
    "ro.product.manufacturer=Google"
    "ro.product.model=Pixel 2 XL"
    "ro.product.device=taimen"
    "ro.product.name=taimen"
    "ro.product.system.brand=google"
    "ro.product.system.device=taimen"
    "ro.product.system.manufacturer=Google"
    "ro.product.system.model=Pixel 2 XL"
    "ro.product.system.name=taimen"
    "ro.build.fingerprint=google/taimen/taimen:10/QQ3A.200805.001/6578210:user/release-keys"
    "ro.system.build.fingerprint=google/taimen/taimen:10/QQ3A.200805.001/6578210:user/release-keys"
    "ro.build.description=taimen-user 10 QQ3A.200805.001 6578210 release-keys"
)

# Metoda 1: Przez Magisk resetprop (wymaga roota)
if adb -s "$DEVICE" shell "su -c 'which resetprop'" 2>/dev/null | grep -q resetprop; then
    echo "[+] Używam resetprop (Magisk)..."
    for prop in "${PROPS[@]}"; do
        key="${prop%%=*}"
        val="${prop#*=}"
        adb -s "$DEVICE" shell "su -c \"resetprop '$key' '$val'\"" && \
            echo "  ✓ $key" || echo "  ✗ $key"
    done
    echo "[+] Props ustawione (tymczasowo do restartu)"
    echo "    Aby zachować po restarcie — użyj MagiskHide Props Config"

# Metoda 2: Przez MagiskHide Props Config (trwałe)
elif adb -s "$DEVICE" shell "su -c 'which props'" 2>/dev/null | grep -q props; then
    echo "[+] MagiskHide Props Config wykryty"
    echo "    Uruchom na telefonie: su → props → 1 (simulation) → wpisz Google Pixel 2 XL"

else
    echo "[!] Brak resetprop lub props"
    echo "    Zainstaluj Magisk moduł: MagiskHide Props Config"
    echo "    https://github.com/Magisk-Modules-Repo/MagiskHidePropsConf"
    echo ""
    echo "    LUB ręcznie w Termux:"
    echo "    su"
    for prop in "${PROPS[@]}"; do
        key="${prop%%=*}"; val="${prop#*=}"
        echo "    resetprop '$key' '$val'"
    done
fi

echo ""
echo "[i] Uwaga: UserAgent i device fingerprint w usługach Google"
echo "    zostaną zaktualizowane po restarcie aplikacji."
