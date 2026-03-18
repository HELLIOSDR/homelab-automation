"""System sensor — bateria, sieć, RAM, CPU przez Termux:API"""
import subprocess, json, psutil, time

def read() -> dict:
    data = {}

    # Bateria
    try:
        bat_out = subprocess.run(
            ["termux-battery-status"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
        if bat_out:
            data["battery"] = json.loads(bat_out)
    except Exception:
        try:
            data["battery"] = {"percentage": _adb_battery()}
        except Exception:
            pass

    # Sieć
    try:
        net_out = subprocess.run(
            ["termux-wifi-connectioninfo"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
        if net_out:
            wifi = json.loads(net_out)
            data["connectivity"] = {
                "type": "WiFi" if wifi.get("ssid") not in ("", "<unknown ssid>") else "Mobile",
                "ssid": wifi.get("ssid"),
                "signal_strength": wifi.get("rssi", 0),
                "ip": wifi.get("ip", ""),
            }
    except Exception:
        data["connectivity"] = {"type": "unknown"}

    # RAM / CPU (psutil)
    try:
        mem = psutil.virtual_memory()
        data["memory"] = {
            "total_mb": mem.total // 1024**2,
            "available_mb": mem.available // 1024**2,
            "percent_used": mem.percent,
        }
        data["cpu_percent"] = psutil.cpu_percent(interval=0.5)
    except Exception:
        pass

    # Temperatura (jeśli dostępna)
    try:
        temp_out = subprocess.run(
            ["termux-sensor", "-s", "thermometer", "-n", "1"],
            capture_output=True, text=True, timeout=3
        ).stdout.strip()
        if temp_out:
            t = json.loads(temp_out)
            data["temperature_c"] = t.get("thermometer", {}).get("values", [None])[0]
    except Exception:
        pass

    return data

def _adb_battery() -> int:
    out = subprocess.run(
        ["dumpsys", "battery"],
        capture_output=True, text=True, timeout=3
    ).stdout
    for line in out.splitlines():
        if "level:" in line:
            return int(line.split(":")[1].strip())
    return -1
