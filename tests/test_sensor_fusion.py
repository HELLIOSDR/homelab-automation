"""
tests/test_sensor_fusion.py — testy dla sensor_fusion
"""
import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'agent'))


# ── context_summary ────────────────────────────────────────────────────────────

class TestContextSummary:
    """Testuje funkcję context_summary — nie wymaga hardware"""

    def _import(self):
        # Mockujemy sensory żeby nie wymagać Termux
        mocks = {m: MagicMock() for m in ['sensors.gps','sensors.sms','sensors.camera',
                                           'sensors.motion','sensors.audio','sensors.system','sensors']}
        with patch.dict('sys.modules', mocks):
            import sensor_fusion
            return sensor_fusion

    def test_full_context_summary(self):
        sf = self._import()
        ctx = {
            "battery": {"level": 75, "charging": False},
            "connectivity": {"type": "wifi"},
            "location": {"lat": 52.2297, "lon": 21.0122, "stale": False},
            "motion": {"shake": False},
            "sms_count_pending": 2,
        }
        summary = sf.context_summary(ctx)
        assert "75%" in summary
        assert "wifi" in summary
        assert "GPS" in summary
        assert "2 SMS" in summary

    def test_empty_context_returns_no_data(self):
        sf = self._import()
        assert sf.context_summary({}) == "no data"

    def test_charging_shows_bolt(self):
        sf = self._import()
        ctx = {"battery": {"level": 50, "charging": True}, "connectivity": {}, "location": {}, "motion": {}}
        summary = sf.context_summary(ctx)
        assert "⚡" in summary

    def test_not_charging_shows_battery(self):
        sf = self._import()
        ctx = {"battery": {"level": 50, "charging": False}, "connectivity": {}, "location": {}, "motion": {}}
        summary = sf.context_summary(ctx)
        assert "🔋" in summary

    def test_shake_shown_in_summary(self):
        sf = self._import()
        ctx = {"battery": {}, "connectivity": {}, "location": {}, "motion": {"shake": True}}
        summary = sf.context_summary(ctx)
        assert "SHAKE" in summary

    def test_stale_gps_shown(self):
        sf = self._import()
        ctx = {"battery": {}, "connectivity": {}, "location": {"stale": True, "lat": None, "lon": None}, "motion": {}}
        summary = sf.context_summary(ctx)
        assert "stale" in summary

    def test_no_sms_not_shown(self):
        sf = self._import()
        ctx = {"battery": {}, "connectivity": {}, "location": {}, "motion": {}, "sms_count_pending": 0}
        summary = sf.context_summary(ctx)
        assert "SMS" not in summary


# ── get_current ────────────────────────────────────────────────────────────────

class TestGetCurrent:

    def _import(self):
        mocks = {m: MagicMock() for m in ['sensors.gps','sensors.sms','sensors.camera',
                                           'sensors.motion','sensors.audio','sensors.system','sensors']}
        with patch.dict('sys.modules', mocks):
            import sensor_fusion
            return sensor_fusion

    def test_initial_context_is_empty_dict(self):
        sf = self._import()
        assert isinstance(sf.get_current(), dict)
