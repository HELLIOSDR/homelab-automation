"""
tests/test_sensors.py — testy sensorów (bez Termux, z mockami subprocess)
"""
import pytest, sys, os, json, math
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'agent'))


# ── GPS ────────────────────────────────────────────────────────────────────────

class TestGPS:
    def _gps(self):
        if 'sensors.gps' in sys.modules: del sys.modules['sensors.gps']
        from sensors import gps; return gps

    def _run(self, stdout="", returncode=0):
        m = MagicMock(); m.stdout = stdout; m.returncode = returncode; return m

    def test_valid_read_returns_coords(self):
        gps = self._gps()
        payload = json.dumps({"latitude": 52.23, "longitude": 21.01, "accuracy": 10})
        with patch('subprocess.run', return_value=self._run(payload)):
            result = gps.read()
        assert result["latitude"] == 52.23
        assert result["longitude"] == 21.01

    def test_empty_output_returns_empty(self):
        gps = self._gps()
        with patch('subprocess.run', return_value=self._run("")):
            result = gps.read()
        assert result == {}

    def test_error_returns_stale_last(self):
        gps = self._gps()
        gps._last = {"latitude": 52.0, "longitude": 21.0}
        with patch('subprocess.run', side_effect=Exception("timeout")):
            result = gps.read()
        assert result.get("stale") is True
        assert result["latitude"] == 52.0

    def test_haversine_same_point_is_zero(self):
        gps = self._gps()
        assert gps._haversine(52.0, 21.0, 52.0, 21.0) == 0.0

    def test_haversine_known_distance(self):
        gps = self._gps()
        # Warszawa → Kraków ≈ 252km
        d = gps._haversine(52.2297, 21.0122, 50.0647, 19.9450)
        assert 250000 < d < 255000

    def test_moving_when_far_from_last(self):
        gps = self._gps()
        gps._last = {"latitude": 52.0, "longitude": 21.0}
        assert gps._is_moving({"latitude": 52.001, "longitude": 21.001})  # ~130m

    def test_not_moving_when_close(self):
        gps = self._gps()
        gps._last = {"latitude": 52.0, "longitude": 21.0}
        assert not gps._is_moving({"latitude": 52.00001, "longitude": 21.00001})  # ~1m


# ── Motion ─────────────────────────────────────────────────────────────────────

class TestMotion:
    def _motion(self):
        if 'sensors.motion' in sys.modules: del sys.modules['sensors.motion']
        from sensors import motion; return motion

    def _run(self, stdout="", returncode=0):
        m = MagicMock(); m.stdout = stdout; m.returncode = returncode; return m

    def test_shake_detected_above_threshold(self):
        motion = self._motion()
        # Duże przyspieszenie — wstrząs
        payload = json.dumps({"accelerometer": {"values": [0, 0, 20.0]}})
        with patch('subprocess.run', return_value=self._run(payload)):
            result = motion.read()
        assert result["accelerometer"]["shake"] is True

    def test_no_shake_at_rest(self):
        motion = self._motion()
        payload = json.dumps({"accelerometer": {"values": [0, 0, 9.8]}})
        with patch('subprocess.run', return_value=self._run(payload)):
            result = motion.read()
        assert result["accelerometer"]["shake"] is False

    def test_magnitude_calculated_correctly(self):
        motion = self._motion()
        payload = json.dumps({"accelerometer": {"values": [3.0, 4.0, 0.0]}})
        with patch('subprocess.run', return_value=self._run(payload)):
            result = motion.read()
        assert abs(result["accelerometer"]["magnitude"] - 5.0) < 0.01

    def test_subprocess_error_returns_empty(self):
        motion = self._motion()
        with patch('subprocess.run', side_effect=Exception("timeout")):
            result = motion.read()
        assert result == {}


# ── System ─────────────────────────────────────────────────────────────────────

class TestSystem:
    def _system(self):
        if 'sensors.system' in sys.modules: del sys.modules['sensors.system']
        from sensors import system; return system

    def _run(self, stdout="", returncode=0):
        m = MagicMock(); m.stdout = stdout; m.returncode = returncode; return m

    def test_battery_parsed(self):
        system = self._system()
        bat = json.dumps({"percentage": 78, "status": "discharging", "plugged": "unplugged"})
        wifi = json.dumps({"ssid": "HomeNet", "rssi": -55, "ip": "192.168.1.2"})
        responses = [self._run(bat), self._run(wifi), self._run("")]
        with patch('subprocess.run', side_effect=responses):
            result = system.read()
        assert result["battery"]["percentage"] == 78

    def test_psutil_memory_always_available(self):
        """psutil nie wymaga Termux — powinno zawsze działać"""
        system = self._system()
        with patch('subprocess.run', side_effect=Exception("no termux")):
            result = system.read()
        # memory z psutil powinno działać nawet bez Termux
        assert "memory" in result
        assert result["memory"]["total_mb"] > 0

    def test_adb_battery_parses_level(self):
        system = self._system()
        dumpsys_output = "  level: 42\n  scale: 100\n"
        with patch('subprocess.run', return_value=self._run(dumpsys_output)):
            level = system._adb_battery()
        assert level == 42
