"""
healthcheck.py — sprawdza środowisko przed startem Helios
Uruchom: python3 healthcheck.py
Zwraca: 0 = OK, 1 = błędy krytyczne
"""
import sys
import os

OK, WARN, FAIL = "✓", "⚠", "✗"
errors = 0
warnings = 0

def check(label, condition, critical=True, hint=""):
    global errors, warnings
    if condition:
        print(f"  {OK} {label}")
    else:
        if critical:
            print(f"  {FAIL} {label}" + (f"  → {hint}" if hint else ""))
            errors += 1
        else:
            print(f"  {WARN} {label}" + (f"  → {hint}" if hint else ""))
            warnings += 1

print("=== Helios healthcheck ===\n")

# Python
print("[Python]")
check("Python 3.9+", sys.version_info >= (3, 9), hint="wymagane 3.9+")

# Zależności
print("\n[Zależności]")
deps = {
    "anthropic": True,
    "fastapi": True,
    "uvicorn": True,
    "aiohttp": True,
    "requests": True,
    "dotenv": True,
    "pydantic": True,
    "psutil": False,  # nie krytyczne
}
for dep, critical in deps.items():
    try:
        __import__(dep)
        check(dep, True, critical)
    except ImportError:
        check(dep, False, critical, hint="pip install " + dep.replace("dotenv", "python-dotenv"))

# Env
print("\n[Konfiguracja]")
env_file = os.path.expanduser("~/ai_agent/.env")
check(".env istnieje", os.path.exists(env_file), critical=False, hint=f"skopiuj config/.env.example → {env_file}")

api_key = os.getenv("ANTHROPIC_API_KEY", "")
check("ANTHROPIC_API_KEY ustawiony", bool(api_key), hint="wymagany dla Level2 (Claude API)")

allowed = os.getenv("ALLOWED_NUMBERS", "")
check("ALLOWED_NUMBERS ustawiony", bool(allowed), critical=False, hint="numery SMS komend")

# Podsumowanie
print(f"\n{'='*26}")
if errors == 0 and warnings == 0:
    print("Wszystko OK — można startować.")
elif errors == 0:
    print(f"OK z {warnings} ostrzeżeniami — można startować.")
else:
    print(f"BŁĄD: {errors} krytycznych problemów — napraw przed startem.")

sys.exit(1 if errors else 0)
