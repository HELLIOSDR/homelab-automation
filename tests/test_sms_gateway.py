"""
tests/test_sms_gateway.py — testy homelab/sms_gateway.py
"""
import pytest, sys, os
from unittest.mock import patch, AsyncMock, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'homelab'))

def _load():
    for k in list(sys.modules.keys()):
        if 'sms_gateway' in k: del sys.modules[k]
    mocks = {'uvicorn': MagicMock(), 'dotenv': MagicMock()}
    mocks['dotenv'].load_dotenv = MagicMock()
    env = {'PHONE_API_URL':'http://phone:7788','PHONE_API_TOKEN':'test-token',
           'GATEWAY_PORT':'8080','AGENT_NAME':'Helios'}
    with patch.dict('sys.modules', mocks):
        with patch('os.getenv', side_effect=lambda k, d='': env.get(k, d)):
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "sms_gateway",
                os.path.join(os.path.dirname(__file__),'..','homelab','sms_gateway.py'))
            mod = importlib.util.module_from_spec(spec)
            with patch.dict('sys.modules', mocks):
                spec.loader.exec_module(mod)
    return mod


class TestModels:
    def test_send_sms_request(self):
        gw = _load()
        r = gw.SendSMSRequest(to="+48123456789", text="Test")
        assert r.to == "+48123456789"
        assert r.text == "Test"

    def test_query_defaults(self):
        gw = _load()
        r = gw.QueryRequest(prompt="gdzie jesteś?")
        assert r.include_photo is False
        assert r.include_sensor_context is True

    def test_webhook_defaults(self):
        gw = _load()
        ev = gw.WebhookSMSEvent(from_number="+48999", text="hello")
        assert ev.timestamp == ""

    def test_webhook_timestamp(self):
        gw = _load()
        ev = gw.WebhookSMSEvent(from_number="+48999", text="ok", timestamp="2026-04-03")
        assert "2026" in ev.timestamp


class TestPhoneHelpers:
    @pytest.mark.asyncio
    async def test_phone_get_returns_json(self):
        gw = _load()
        mock_resp = AsyncMock()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_resp.json = AsyncMock(return_value={"status": "alive"})

        mock_sess = AsyncMock()
        mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
        mock_sess.__aexit__ = AsyncMock(return_value=False)
        mock_sess.get = AsyncMock(return_value=mock_resp)

        with patch.object(gw.aiohttp, 'ClientSession', return_value=mock_sess):
            result = await gw.phone_get("/v1/health")
        assert result == {"status": "alive"}

    @pytest.mark.asyncio
    async def test_phone_post_returns_json(self):
        gw = _load()
        mock_resp = AsyncMock()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_resp.json = AsyncMock(return_value={"sent": True})

        mock_sess = AsyncMock()
        mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
        mock_sess.__aexit__ = AsyncMock(return_value=False)
        mock_sess.post = AsyncMock(return_value=mock_resp)

        with patch.object(gw.aiohttp, 'ClientSession', return_value=mock_sess):
            result = await gw.phone_post("/v1/sms/send", {"to": "+48123", "text": "hi"})
        assert result == {"sent": True}


class TestConfig:
    def test_phone_url(self):
        gw = _load()
        assert gw.PHONE_API_URL == "http://phone:7788"

    def test_agent_name(self):
        gw = _load()
        assert gw.AGENT_NAME == "Helios"

    def test_auth_header(self):
        gw = _load()
        assert "Authorization" in gw._phone_headers
        assert "test-token" in gw._phone_headers["Authorization"]
