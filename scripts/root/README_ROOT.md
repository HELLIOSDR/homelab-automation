# Root Samsung Galaxy A23 5G — Krok po kroku

## Wymagania
- Linux na PC z ADB i Heimdall
- Kabel USB
- ~2h czasu + kopia zapasowa danych (reset do ustawień fabrycznych NIE jest wymagany, ale możliwy)

## KROK 0 — Backup
Zanim cokolwiek zrobisz: **zrób backup danych telefonu.**
Zdjęcia, kontakty, aplikacje — wszystko.

## KROK 1 — Włącz Opcje Programistyczne
1. **Ustawienia** → **O telefonie** → kliknij `Numer kompilacji` **7 razy**
2. Pojawi się: "Jesteś teraz programistą!"

## KROK 2 — Włącz OEM Unlocking + USB Debugging
1. **Ustawienia** → **Opcje programistyczne**:
   - **OEM unlocking** → WŁĄCZ (może wymagać SIM lub konta Samsung)
   - **Debugowanie USB** → WŁĄCZ
2. Podłącz USB do PC
3. Na telefonie: **Zezwól** na debugowanie USB z tego komputera

Weryfikacja:
```bash
adb devices  # powinno pokazać urządzenie (nie "unauthorized")
```

## KROK 3 — Sprawdź urządzenie
```bash
bash scripts/adb/check_device.sh
```
Zapisuje profil do `config/device_profile.json`.

## KROK 4 — Pobierz stock firmware
Pobierz pełne firmware dla swojego wariantu (SM-A236B / SM-A236U):
- https://samfw.com → wpisz model + region
- Lub Frija (narzędzie GUI do pobierania firmware Samsung)

Wypakuj ZIP → znajdź `AP_*.tar.md5` → wypakuj → znajdź `boot.img` lub `boot.img.lz4`.

Jeśli `.lz4`:
```bash
lz4 -d boot.img.lz4 boot.img
```

## KROK 5 — Patchuj boot.img przez Magisk
```bash
bash scripts/root/prepare_root.sh  # instaluje Magisk APK na telefonie
```
Na telefonie:
1. Otwórz **Magisk** → **Install** → **Select and Patch a File**
2. Wybierz `boot.img` z /sdcard/
3. Magisk zapisze `magisk_patched_XXXXX.img` w `/sdcard/Download/`

Skopiuj na PC:
```bash
adb pull /sdcard/Download/magisk_patched_*.img .root_work/magisk_patched_boot.img
```

## KROK 6 — Flash przez Heimdall
Wejdź w **Download Mode**:
- Wyłącz telefon
- Przytrzymaj `Vol Down` → podłącz kabel USB
- Ekran pokaże "Downloading..."

```bash
bash scripts/root/flash_magisk.sh
```

## KROK 7 — Weryfikacja
Po restarcie, otwórz Magisk (może zapytać o dodatkową konfigurację — zatwierdź).

```bash
bash scripts/root/verify_root.sh
```

## Co dalej?
Masz root → instaluj Termux i agenta:
```bash
bash scripts/termux/install_termux.sh
bash scripts/termux/setup_ssh.sh
```

## Troubleshooting

| Problem | Rozwiązanie |
|---------|-------------|
| `heimdall: device not found` | Zainstaluj reguły udev: patrz flash_magisk.sh |
| OEM unlocking wyszarzone | Potrzebne konto Samsung lub aktywna SIM |
| Telefon bootloop | Wejdź w recovery → factory reset (niestety traci dane) |
| Magisk nie widzi boot.img | Upewnij się że to poprawna wersja firmware |
| `adb: unauthorized` | Na telefonie: odwołaj dostęp ADB i zatwierdź ponownie |
