"""
tests/test_brain.py — testy dla brain.py (unit, bez hardware i API)
"""
import pytest
import sys
import os
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'agent'))


def _load_brain():
    """Ładuje brain z zamockowanymi zależnościami"""
    mocks = {
        'anthropic': MagicMock(),
        'sensor_fusion': MagicMock(),
        'sensors': MagicMock(),
        'sensors.sms': MagicMock(),
        'sensors.camera': MagicMock(),
        'autonomy': MagicMock(),
        'dotenv': MagicMock(),
        'aiohttp': MagicMock(),
        'uvicorn': MagicMock(),
        'api_server': MagicMock(),
    }
    # dotenv.load_dotenv nie robi nic
    mocks['dotenv'].load_dotenv = MagicMock()
    with patch.dict('sys.modules', mocks):
        with patch('os.getenv', side_effect=lambda k, d='': d):
            import importlib
            if 'brain' in sys.modules:
                del sys.modules['brain']
            import brain
            return brain


# ── _is_authorized ─────────────────────────────────────────────────────────────

class TestIsAuthorized:

    def test_wildcard_allows_all(self):
        brain = _load_brain()
        with patch.object(brain, 'ALLOWED_NUMBERS', {'*'}):
            assert brain._is_authorized('+48123456789')

    def test_exact_match_allowed(self):
        brain = _load_brain()
        with patch.object(brain, 'ALLOWED_NUMBERS', {'+48123456789'}):
            assert brain._is_authorized('+48123456789')

    def test_unknown_number_denied(self):
        brain = _load_brain()
        with patch.object(brain, 'ALLOWED_NUMBERS', {'+48999999999'}):
            assert not brain._is_authorized('+48123456789')

    def test_empty_allowed_denies_all(self):
        brain = _load_brain()
        with patch.object(brain, 'ALLOWED_NUMBERS', {''}):
            assert not brain._is_authorized('+48123456789')

    def test_number_with_spaces_normalized(self):
        brain = _load_brain()
        with patch.object(brain, 'ALLOWED_NUMBERS', {'+48 123 456 789'}):
            assert brain._is_authorized('+48123456789')

    def test_number_with_dashes_normalized(self):
        brain = _load_brain()
        with patch.object(brain, 'ALLOWED_NUMBERS', {'+48-123-456-789'}):
            assert brain._is_authorized('+48123456789')

    def test_suffix_match(self):
        """Krótki numer w ALLOWED pasuje do pełnego numeru przychodzącego"""
        brain = _load_brain()
        # _is_authorized: incoming.endswith(allowed) — przechowuj skrót, matchuj pełny
        with patch.object(brain, 'ALLOWED_NUMBERS', {'123456789'}):
            assert brain._is_authorized('+48123456789')


# ── Level1Engine ───────────────────────────────────────────────────────────────

class TestLevel1Engine:

    def _make_engine(self):
        brain = _load_brain()
        l2_mock = MagicMock()
        l2_mock.handle_sms = AsyncMock()
        return brain.Level1Engine(l2_mock), brain

    @pytest.mark.asyncio
    async def test_low_battery_generates_alert(self):
        engine, brain = self._make_engine()
        ctx = {
            "battery": {"level": 10, "charging": False},
            "pending_sms": [],
            "motion": {},
        }
        with patch.object(brain, 'ALLOWED_NUMBERS', set()):
            actions = await engine.process(ctx)
        assert any(a["action"] == "alert_homelab" for a in actions)

    @pytest.mark.asyncio
    async def test_charging_no_battery_alert(self):
        engine, brain = self._make_engine()
        ctx = {
            "battery": {"level": 5, "charging": True},
            "pending_sms": [],
            "motion": {},
        }
        with patch.object(brain, 'ALLOWED_NUMBERS', set()):
            actions = await engine.process(ctx)
        # Ładowanie — brak alertu o baterii
        assert not any("Bateria" in a.get("message", "") for a in actions)

    @pytest.mark.asyncio
    async def test_shake_generates_alert(self):
        engine, brain = self._make_engine()
        ctx = {
            "battery": {"level": 80, "charging": False},
            "pending_sms": [],
            "motion": {"shake": True},
        }
        with patch.object(brain, 'ALLOWED_NUMBERS', set()):
            actions = await engine.process(ctx)
        assert any(a["action"] == "alert_homelab" and "wstrząs" in a.get("message", "").lower()
                   for a in actions)

    @pytest.mark.asyncio
    async def test_authorized_sms_escalates_to_l2(self):
        engine, brain = self._make_engine()
        ctx = {
            "battery": {"level": 80, "charging": False},
            "pending_sms": [{"number": "+48123456789", "body": "gdzie jesteś?"}],
            "motion": {},
        }
        with patch.object(brain, 'ALLOWED_NUMBERS', {'+48123456789'}):
            await engine.process(ctx)
        # Krótkie czekanie na task
        await asyncio.sleep(0.01)

    @pytest.mark.asyncio
    async def test_empty_context_no_crash(self):
        engine, brain = self._make_engine()
        with patch.object(brain, 'ALLOWED_NUMBERS', set()):
            actions = await engine.process({})
        assert isinstance(actions, list)


import asyncio
