"""
tests/test_api_server.py — testy dla agent/api_server.py
FastAPI TestClient z zamockowanymi sensor_fusion, sms i camera.
Nie wymaga realnego hardware ani kluczy API.
"""
import sys
import os
import base64
import importlib
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'agent'))


# ── Helpers ────────────────────────────────────────────────────────────────────

_FAKE_CTX = {
    "timestamp": "2026-04-03T12:00:00+00:00",
    "battery": {"level": 80, "charging": False},
    "connectivity": {"type": "wifi", "ip": "192.168.1.10"},
    "location": {"lat": 52.2297, "lon": 21.0122, "accuracy_m": 10, "stale": False},
    "motion": {"shake": False},
    "sms_count_pending": 0,
}

_SENSOR_MOCKS = {
    'sensor_fusion': MagicMock(),
    'sensors': MagicMock(),
    'sensors.sms': MagicMock(),
    'sensors.camera': MagicMock(),
}


def _make_sensor_fusion_mock():
    sf = MagicMock()
    sf.snapshot = AsyncMock(return_value=dict(_FAKE_CTX))
    sf.get_current = MagicMock(return_value=dict(_FAKE_CTX))
    sf.context_summary = MagicMock(return_value="80% wifi GPS")
    return sf


def _load_app(l2_brain=None, token=""):
    """Ładuje create_app z wszystkimi zależnościami zamockowanymi.

    api_server robi 'from sensors import sms as sms_sensor, camera', więc po
    imporcie moduł trzyma referencje do atrybutów sensors_mock.sms i
    sensors_mock.camera — nie do naszych osobnych mocków. Musimy po imporcie
    zamienić te atrybuty na sterowane MagicMock.
    """
    sf_mock = _make_sensor_fusion_mock()
    sensors_mock = MagicMock()

    mocks = {
        'sensor_fusion': sf_mock,
        'sensors': sensors_mock,
        'sensors.sms': sensors_mock.sms,
        'sensors.camera': sensors_mock.camera,
    }

    with patch.dict('sys.modules', mocks):
        with patch.dict('os.environ', {'API_TOKEN': token, 'AGENT_NAME': 'TestAgent'}):
            if 'api_server' in sys.modules:
                del sys.modules['api_server']
            import api_server
            app = api_server.create_app(l2_brain=l2_brain)

    # Po imporcie api_server trzyma referencje do sensors_mock.sms i .camera
    # Możemy sterować nimi przez te atrybuty.
    sms_mock = sensors_mock.sms
    sms_mock.send = MagicMock(return_value=True)
    camera_mock = sensors_mock.camera

    return app, sf_mock, sms_mock, camera_mock, api_server


# ── Testy: GET /v1/health ──────────────────────────────────────────────────────

class TestHealthEndpoint:

    def test_health_returns_alive(self):
        from fastapi.testclient import TestClient
        app, sf, *_ = _load_app()
        with TestClient(app) as client:
            resp = client.get("/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "alive"

    def test_health_contains_agent_name(self):
        from fastapi.testclient import TestClient
        app, sf, *_ = _load_app()
        with TestClient(app) as client:
            resp = client.get("/v1/health")
        assert resp.json()["agent"] == "TestAgent"

    def test_health_contains_battery(self):
        from fastapi.testclient import TestClient
        app, sf, *_ = _load_app()
        with TestClient(app) as client:
            resp = client.get("/v1/health")
        data = resp.json()
        assert "battery" in data
        assert data["battery"]["level"] == 80

    def test_health_contains_api_version(self):
        from fastapi.testclient import TestClient
        app, sf, *_ = _load_app()
        with TestClient(app) as client:
            resp = client.get("/v1/health")
        assert resp.json()["api_version"] == "1.0.0"

    def test_health_context_age_is_int_or_none(self):
        from fastapi.testclient import TestClient
        app, sf, *_ = _load_app()
        with TestClient(app) as client:
            resp = client.get("/v1/health")
        age = resp.json().get("context_age_s")
        assert age is None or isinstance(age, int)

    def test_health_no_auth_required_when_no_token_set(self):
        from fastapi.testclient import TestClient
        app, *_ = _load_app(token="")
        with TestClient(app) as client:
            resp = client.get("/v1/health")
        assert resp.status_code == 200


# ── Testy: GET /v1/context ─────────────────────────────────────────────────────

class TestContextEndpoint:

    def test_context_returns_200(self):
        from fastapi.testclient import TestClient
        app, sf, *_ = _load_app()
        with TestClient(app) as client:
            resp = client.get("/v1/context")
        assert resp.status_code == 200

    def test_context_has_battery(self):
        from fastapi.testclient import TestClient
        app, sf, *_ = _load_app()
        with TestClient(app) as client:
            resp = client.get("/v1/context")
        assert resp.json()["battery"]["level"] == 80

    def test_context_no_last_photo_in_base_response(self):
        """last_photo (base64) powinno być usunięte z odpowiedzi"""
        from fastapi.testclient import TestClient
        ctx_with_photo = dict(_FAKE_CTX)
        ctx_with_photo["last_photo"] = {
            "path": "/tmp/photo.jpg",
            "size_kb": 200,
            "base64": "abc123",
        }
        app, sf, *_ = _load_app()
        sf.snapshot = AsyncMock(return_value=ctx_with_photo)
        with TestClient(app) as client:
            resp = client.get("/v1/context")
        data = resp.json()
        # base64 nie może wyciec — albo brak last_photo albo brak klucza base64
        if "last_photo" in data:
            assert "base64" not in data["last_photo"]
        else:
            assert True  # poprawnie usunięte

    def test_context_with_photo_flag_adds_photo_url(self):
        """Przy ?photo=true w odpowiedzi pojawia się photo_url"""
        from fastapi.testclient import TestClient
        ctx_with_photo = dict(_FAKE_CTX)
        ctx_with_photo["last_photo"] = {
            "path": "/tmp/photo.jpg",
            "size_kb": 200,
            "base64": "abc123",
        }
        app, sf, *_ = _load_app()
        sf.snapshot = AsyncMock(return_value=ctx_with_photo)
        with TestClient(app) as client:
            resp = client.get("/v1/context?photo=true")
        data = resp.json()
        assert "last_photo" in data
        assert data["last_photo"]["photo_url"] == "/v1/photo/latest"

    def test_context_calls_snapshot(self):
        from fastapi.testclient import TestClient
        app, sf, *_ = _load_app()
        with TestClient(app) as client:
            client.get("/v1/context")
        sf.snapshot.assert_called_once()

    def test_context_auth_required_when_token_set(self):
        from fastapi.testclient import TestClient
        app, *_ = _load_app(token="secret123")
        with TestClient(app) as client:
            resp = client.get("/v1/context")
        assert resp.status_code == 401

    def test_context_auth_passes_with_correct_token(self):
        from fastapi.testclient import TestClient
        app, *_ = _load_app(token="secret123")
        with TestClient(app) as client:
            resp = client.get(
                "/v1/context",
                headers={"Authorization": "Bearer secret123"},
            )
        assert resp.status_code == 200

    def test_context_auth_fails_with_wrong_token(self):
        from fastapi.testclient import TestClient
        app, *_ = _load_app(token="secret123")
        with TestClient(app) as client:
            resp = client.get(
                "/v1/context",
                headers={"Authorization": "Bearer wrong"},
            )
        assert resp.status_code == 403


# ── Testy: POST /v1/sms/send ───────────────────────────────────────────────────

class TestSmsSendEndpoint:

    def test_sms_send_returns_success_true(self):
        from fastapi.testclient import TestClient
        app, sf, sms_mock, *_ = _load_app()
        with TestClient(app) as client:
            resp = client.post("/v1/sms/send", json={"to": "+48123456789", "text": "Hello"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_sms_send_returns_recipient(self):
        from fastapi.testclient import TestClient
        app, sf, sms_mock, *_ = _load_app()
        with TestClient(app) as client:
            resp = client.post("/v1/sms/send", json={"to": "+48123456789", "text": "Hello"})
        assert resp.json()["to"] == "+48123456789"

    def test_sms_send_returns_length(self):
        from fastapi.testclient import TestClient
        app, sf, sms_mock, *_ = _load_app()
        with TestClient(app) as client:
            resp = client.post("/v1/sms/send", json={"to": "+48000000000", "text": "Hi there"})
        assert resp.json()["length"] == len("Hi there")

    def test_sms_send_calls_sensor_send(self):
        from fastapi.testclient import TestClient
        app, sf, sms_mock, *_ = _load_app()
        with TestClient(app) as client:
            client.post("/v1/sms/send", json={"to": "+48999999999", "text": "Test"})
        sms_mock.send.assert_called_once_with("+48999999999", "Test")

    def test_sms_send_failure_returns_false(self):
        from fastapi.testclient import TestClient
        app, sf, sms_mock, *_ = _load_app()
        sms_mock.send = MagicMock(return_value=False)
        with TestClient(app) as client:
            resp = client.post("/v1/sms/send", json={"to": "+48000000000", "text": "Fail"})
        assert resp.json()["success"] is False

    def test_sms_send_missing_fields_422(self):
        from fastapi.testclient import TestClient
        app, *_ = _load_app()
        with TestClient(app) as client:
            resp = client.post("/v1/sms/send", json={"to": "+48000000000"})
        assert resp.status_code == 422


# ── Testy: POST /v1/messages ───────────────────────────────────────────────────

class TestMessagesEndpoint:

    def _basic_req(self, **kwargs):
        base = {
            "messages": [{"role": "user", "content": "status"}],
            "include_sensor_context": True,
        }
        base.update(kwargs)
        return base

    def test_messages_returns_message_type(self):
        from fastapi.testclient import TestClient
        app, *_ = _load_app()
        with TestClient(app) as client:
            resp = client.post("/v1/messages", json=self._basic_req())
        assert resp.status_code == 200
        assert resp.json()["type"] == "message"

    def test_messages_role_is_assistant(self):
        from fastapi.testclient import TestClient
        app, *_ = _load_app()
        with TestClient(app) as client:
            resp = client.post("/v1/messages", json=self._basic_req())
        assert resp.json()["role"] == "assistant"

    def test_messages_content_is_list_with_text(self):
        from fastapi.testclient import TestClient
        app, *_ = _load_app()
        with TestClient(app) as client:
            resp = client.post("/v1/messages", json=self._basic_req())
        content = resp.json()["content"]
        assert isinstance(content, list)
        assert content[0]["type"] == "text"
        assert isinstance(content[0]["text"], str)

    def test_messages_has_id(self):
        from fastapi.testclient import TestClient
        app, *_ = _load_app()
        with TestClient(app) as client:
            resp = client.post("/v1/messages", json=self._basic_req())
        assert resp.json()["id"].startswith("msg_")

    def test_messages_has_usage(self):
        from fastapi.testclient import TestClient
        app, *_ = _load_app()
        with TestClient(app) as client:
            resp = client.post("/v1/messages", json=self._basic_req())
        usage = resp.json()["usage"]
        assert "input_tokens" in usage
        assert "output_tokens" in usage

    def test_messages_sensor_context_included_when_requested(self):
        from fastapi.testclient import TestClient
        app, *_ = _load_app()
        with TestClient(app) as client:
            resp = client.post("/v1/messages", json=self._basic_req(include_sensor_context=True))
        assert resp.json()["sensor_context"] is not None

    def test_messages_sensor_context_null_when_excluded(self):
        from fastapi.testclient import TestClient
        app, *_ = _load_app()
        with TestClient(app) as client:
            resp = client.post("/v1/messages", json=self._basic_req(include_sensor_context=False))
        assert resp.json()["sensor_context"] is None

    def test_messages_no_user_message_returns_400(self):
        from fastapi.testclient import TestClient
        app, *_ = _load_app()
        with TestClient(app) as client:
            resp = client.post("/v1/messages", json={"messages": [{"role": "assistant", "content": "hi"}]})
        assert resp.status_code == 400

    def test_messages_with_l2_brain_calls_query(self):
        from fastapi.testclient import TestClient
        brain_mock = MagicMock()
        brain_mock.query = AsyncMock(return_value={
            "text": "Odpowiedź L2",
            "model": "claude-3-opus",
            "tokens": 42,
            "context_summary": "80% wifi",
        })
        app, *_ = _load_app(l2_brain=brain_mock)
        with TestClient(app) as client:
            resp = client.post("/v1/messages", json=self._basic_req())
        assert resp.status_code == 200
        brain_mock.query.assert_called_once()
        assert resp.json()["content"][0]["text"] == "Odpowiedź L2"

    def test_messages_content_as_list_of_dicts(self):
        """Obsługa content jako listy słowników"""
        from fastapi.testclient import TestClient
        app, *_ = _load_app()
        req = {
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "bateria?"}]}
            ]
        }
        with TestClient(app) as client:
            resp = client.post("/v1/messages", json=req)
        assert resp.status_code == 200

    def test_messages_stop_reason_end_turn(self):
        from fastapi.testclient import TestClient
        app, *_ = _load_app()
        with TestClient(app) as client:
            resp = client.post("/v1/messages", json=self._basic_req())
        assert resp.json()["stop_reason"] == "end_turn"

    def test_messages_without_sensor_context_no_snapshot_call(self):
        from fastapi.testclient import TestClient
        app, sf, *_ = _load_app()
        with TestClient(app) as client:
            client.post("/v1/messages", json=self._basic_req(include_sensor_context=False))
        sf.snapshot.assert_not_called()


# ── Testy: GET /v1/photo ───────────────────────────────────────────────────────

class TestPhotoEndpoint:

    def test_photo_returns_jpeg_bytes(self):
        from fastapi.testclient import TestClient
        # Małe prawidłowe JPEG (1x1 px)
        tiny_jpeg = (
            b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
            b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t'
            b'\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a'
            b'\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\x1e\xc2'
            b'\xff\xd9'
        )
        fake_b64 = base64.b64encode(tiny_jpeg).decode()
        app, sf, sms_mock, camera_mock, api_mod = _load_app()
        camera_mock.capture = MagicMock(return_value={"base64": fake_b64, "path": "/tmp/p.jpg"})
        with TestClient(app) as client:
            resp = client.get("/v1/photo")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/jpeg"

    def test_photo_calls_camera_capture(self):
        from fastapi.testclient import TestClient
        tiny_jpeg = b'\xff\xd8\xff\xd9'
        fake_b64 = base64.b64encode(tiny_jpeg).decode()
        app, sf, sms_mock, camera_mock, _ = _load_app()
        camera_mock.capture = MagicMock(return_value={"base64": fake_b64})
        with TestClient(app) as client:
            client.get("/v1/photo")
        camera_mock.capture.assert_called_once()

    def test_photo_camera_error_returns_500(self):
        from fastapi.testclient import TestClient
        app, sf, sms_mock, camera_mock, _ = _load_app()
        camera_mock.capture = MagicMock(return_value={"error": "kamera niedostępna"})
        with TestClient(app) as client:
            resp = client.get("/v1/photo")
        assert resp.status_code == 500

    def test_photo_cam_param_passed_to_capture(self):
        from fastapi.testclient import TestClient
        tiny_jpeg = b'\xff\xd8\xff\xd9'
        fake_b64 = base64.b64encode(tiny_jpeg).decode()
        app, sf, sms_mock, camera_mock, _ = _load_app()
        camera_mock.capture = MagicMock(return_value={"base64": fake_b64})
        with TestClient(app) as client:
            client.get("/v1/photo?cam=front")
        camera_mock.capture.assert_called_once_with("front")


# ── Testy: Auth globalnie ─────────────────────────────────────────────────────

class TestAuth:

    def test_no_token_env_allows_all_requests(self):
        from fastapi.testclient import TestClient
        app, *_ = _load_app(token="")
        with TestClient(app) as client:
            assert client.get("/v1/health").status_code == 200
            assert client.get("/v1/context").status_code == 200
            resp = client.post("/v1/sms/send", json={"to": "+48000000000", "text": "hi"})
            assert resp.status_code == 200

    def test_malformed_bearer_returns_401(self):
        from fastapi.testclient import TestClient
        app, *_ = _load_app(token="mytoken")
        with TestClient(app) as client:
            resp = client.get("/v1/context", headers={"Authorization": "mytoken"})
        assert resp.status_code == 401
