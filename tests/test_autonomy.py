"""
tests/test_autonomy.py — testy dla modułu autonomy
"""
import asyncio
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'agent'))

from autonomy import ResourceManager, ProactiveIntelligence, IdentityManager, ConnectionGuard


# ── ResourceManager ────────────────────────────────────────────────────────────

class TestResourceManager:

    def setup_method(self):
        self.rm = ResourceManager()

    @pytest.mark.asyncio
    async def test_critical_battery_triggers_alert(self):
        ctx = {"battery": {"level": 3, "charging": False}, "system": {}}
        actions = await self.rm.check(ctx)
        assert any(a["action"] == "alert_homelab" for a in actions)
        assert self.rm.is_power_save

    @pytest.mark.asyncio
    async def test_low_battery_triggers_warning(self):
        ctx = {"battery": {"level": 10, "charging": False}, "system": {}}
        actions = await self.rm.check(ctx)
        assert any("Bateria" in a.get("message", "") for a in actions)

    @pytest.mark.asyncio
    async def test_charging_clears_power_save(self):
        ctx = {"battery": {"level": 3, "charging": False}, "system": {}}
        await self.rm.check(ctx)
        assert self.rm.is_power_save

        ctx2 = {"battery": {"level": 20, "charging": True}, "system": {}}
        await self.rm.check(ctx2)
        assert not self.rm.is_power_save

    @pytest.mark.asyncio
    async def test_full_battery_no_actions(self):
        ctx = {"battery": {"level": 80, "charging": False}, "system": {}}
        actions = await self.rm.check(ctx)
        assert actions == []

    @pytest.mark.asyncio
    async def test_none_battery_no_crash(self):
        ctx = {"battery": {"level": None}, "system": {}}
        actions = await self.rm.check(ctx)
        assert isinstance(actions, list)


# ── ProactiveIntelligence ──────────────────────────────────────────────────────

class TestProactiveIntelligence:

    def setup_method(self):
        self.pi = ProactiveIntelligence()

    @pytest.mark.asyncio
    async def test_no_motion_no_alert(self):
        ctx = {"motion": {"moving": False}, "location": {}}
        actions = await self.pi.analyze(ctx)
        assert actions == []

    @pytest.mark.asyncio
    async def test_motion_history_accumulates(self):
        ctx = {"motion": {"moving": True}, "location": {}}
        for _ in range(10):
            await self.pi.analyze(ctx)
        # historia ruchu rośnie ale jest ograniczona do 60
        assert len(self.pi._motion_history) <= 60

    @pytest.mark.asyncio
    async def test_location_history_accumulates(self):
        ctx = {"motion": {"moving": False}, "location": {"lat": 52.23, "lon": 21.01}}
        for _ in range(5):
            await self.pi.analyze(ctx)
        assert len(self.pi._location_history) == 5

    @pytest.mark.asyncio
    async def test_location_history_max_100(self):
        ctx = {"motion": {"moving": False}, "location": {"lat": 52.23, "lon": 21.01}}
        for _ in range(110):
            await self.pi.analyze(ctx)
        assert len(self.pi._location_history) <= 100

    @pytest.mark.asyncio
    async def test_empty_context_no_crash(self):
        actions = await self.pi.analyze({})
        assert isinstance(actions, list)


# ── IdentityManager ────────────────────────────────────────────────────────────

class TestIdentityManager:

    def test_identity_has_required_fields(self):
        identity = IdentityManager.get_identity()
        assert "name" in identity
        assert "capabilities" in identity
        assert isinstance(identity["capabilities"], list)
        assert len(identity["capabilities"]) > 0

    def test_startup_message_contains_name(self):
        msg = IdentityManager.startup_message()
        assert "Helios" in msg
        assert "AUTONOMICZNY" in msg

    def test_startup_message_is_string(self):
        assert isinstance(IdentityManager.startup_message(), str)


# ── ConnectionGuard ────────────────────────────────────────────────────────────

class TestConnectionGuard:

    def test_dead_pid_returns_false(self):
        assert not ConnectionGuard._is_pid_alive(999999999)

    def test_own_pid_returns_true(self):
        assert ConnectionGuard._is_pid_alive(os.getpid())

    def test_nonexistent_process_returns_false(self):
        assert not ConnectionGuard._is_process_running("__nonexistent_process_xyz__")
