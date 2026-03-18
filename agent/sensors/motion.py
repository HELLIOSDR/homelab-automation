"""Motion sensor — akcelerometr + żyroskop przez Termux:API"""
import subprocess, json, math, time
from collections import deque

_history: deque = deque(maxlen=20)

def read() -> dict:
    data = {}
    try:
        # Akcelerometr
        acc_out = subprocess.run(
            ["termux-sensor", "-s", "accelerometer", "-n", "1"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
        if acc_out:
            acc = json.loads(acc_out)
            values = acc.get("accelerometer", {}).get("values", [0, 0, 9.8])
            mag = math.sqrt(sum(v**2 for v in values))
            _history.append(mag)

            avg = sum(_history) / len(_history) if _history else 9.8
            shake = mag > 15.0  # mocny wstrząs
            moving = abs(mag - avg) > 2.0  # ruch

            data["accelerometer"] = {
                "x": round(values[0], 2),
                "y": round(values[1], 2),
                "z": round(values[2], 2),
                "magnitude": round(mag, 2),
                "shake": shake,
                "moving": moving,
            }
    except Exception:
        pass

    try:
        # Krok-ometr (jeśli dostępny)
        step_out = subprocess.run(
            ["termux-sensor", "-s", "step_counter", "-n", "1"],
            capture_output=True, text=True, timeout=3
        ).stdout.strip()
        if step_out:
            data["steps"] = json.loads(step_out).get("step_counter", {}).get("values", [0])[0]
    except Exception:
        pass

    return data
