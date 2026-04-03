"""
tests/test_sensors_sms_audio.py — testy SMS i audio sensorów (bez Termux, z mockami)
"""
import pytest, sys, os, json
from unittest.mock import patch, MagicMock, mock_open

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'agent'))


def _run(stdout="", returncode=0):
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    return m


# ── SMS ────────────────────────────────────────────────────────────────────────

class TestSMSReadPending:
    def _fresh_sms(self):
        # Reload module and explicitly clear _seen_ids to isolate tests
        if 'sensors.sms' in sys.modules:
            del sys.modules['sensors.sms']
        from sensors import sms
        sms._seen_ids.clear()
        return sms

    def test_returns_all_messages_on_first_call(self):
        sms = self._fresh_sms()
        messages = [{"_id": 1, "body": "hello"}, {"_id": 2, "body": "world"}]
        with patch('subprocess.run', return_value=_run(json.dumps(messages))):
            result = sms.read_pending()
        assert len(result) == 2
        assert result[0]["body"] == "hello"

    def test_deduplication_via_seen_ids(self):
        sms = self._fresh_sms()
        messages = [{"_id": 1, "body": "hello"}, {"_id": 2, "body": "world"}]
        with patch('subprocess.run', return_value=_run(json.dumps(messages))):
            first = sms.read_pending()
        # Second call — same messages, should be filtered by _seen_ids
        with patch('subprocess.run', return_value=_run(json.dumps(messages))):
            second = sms.read_pending()
        assert len(first) == 2
        assert len(second) == 0

    def test_new_message_after_seen(self):
        sms = self._fresh_sms()
        first_batch = [{"_id": 1, "body": "old"}]
        second_batch = [{"_id": 1, "body": "old"}, {"_id": 2, "body": "new"}]
        with patch('subprocess.run', return_value=_run(json.dumps(first_batch))):
            sms.read_pending()
        with patch('subprocess.run', return_value=_run(json.dumps(second_batch))):
            result = sms.read_pending()
        assert len(result) == 1
        assert result[0]["_id"] == 2

    def test_empty_output_returns_empty_list(self):
        sms = self._fresh_sms()
        with patch('subprocess.run', return_value=_run("")):
            result = sms.read_pending()
        assert result == []

    def test_subprocess_exception_returns_empty_list(self):
        sms = self._fresh_sms()
        with patch('subprocess.run', side_effect=Exception("termux not available")):
            result = sms.read_pending()
        assert result == []

    def test_timeout_exception_returns_empty_list(self):
        import subprocess
        sms = self._fresh_sms()
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired(cmd="termux-sms-list", timeout=10)):
            result = sms.read_pending()
        assert result == []

    def test_invalid_json_returns_empty_list(self):
        sms = self._fresh_sms()
        with patch('subprocess.run', return_value=_run("not valid json {")):
            result = sms.read_pending()
        assert result == []

    def test_message_without_id_still_processed(self):
        sms = self._fresh_sms()
        messages = [{"body": "no id here"}]
        with patch('subprocess.run', return_value=_run(json.dumps(messages))):
            result = sms.read_pending()
        assert len(result) == 1

    def test_seen_ids_populated_after_read(self):
        sms = self._fresh_sms()
        messages = [{"_id": 42, "body": "test"}]
        with patch('subprocess.run', return_value=_run(json.dumps(messages))):
            sms.read_pending()
        assert 42 in sms._seen_ids


class TestSMSSend:
    def _fresh_sms(self):
        if 'sensors.sms' in sys.modules:
            del sys.modules['sensors.sms']
        from sensors import sms
        return sms

    def test_send_short_message_calls_subprocess_once(self):
        sms = self._fresh_sms()
        with patch('subprocess.run', return_value=_run()) as mock_run:
            result = sms.send("+48123456789", "Hello!")
        assert result is True
        mock_run.assert_called_once()

    def test_send_returns_true_on_success(self):
        sms = self._fresh_sms()
        with patch('subprocess.run', return_value=_run()):
            result = sms.send("+48123456789", "Test message")
        assert result is True

    def test_send_returns_false_on_exception(self):
        sms = self._fresh_sms()
        with patch('subprocess.run', side_effect=Exception("no termux")):
            result = sms.send("+48123456789", "Test")
        assert result is False

    def test_long_message_split_into_chunks(self):
        sms = self._fresh_sms()
        # 155 * 2 = 310 chars — should split into 2 chunks
        long_text = "A" * 310
        with patch('subprocess.run', return_value=_run()) as mock_run:
            result = sms.send("+48123456789", long_text)
        assert result is True
        assert mock_run.call_count == 2

    def test_exactly_155_chars_single_chunk(self):
        sms = self._fresh_sms()
        text_155 = "B" * 155
        with patch('subprocess.run', return_value=_run()) as mock_run:
            result = sms.send("+48123456789", text_155)
        assert result is True
        assert mock_run.call_count == 1

    def test_chunk_prefix_added_for_multipart(self):
        sms = self._fresh_sms()
        long_text = "X" * 400  # 3 chunks
        captured_calls = []
        def capture(*args, **kwargs):
            captured_calls.append(args[0])
            return _run()
        with patch('subprocess.run', side_effect=capture):
            sms.send("+48123456789", long_text)
        # First chunk should have [1/3] prefix
        assert "[1/3]" in captured_calls[0][-1]
        assert "[2/3]" in captured_calls[1][-1]
        assert "[3/3]" in captured_calls[2][-1]

    def test_send_short_message_no_prefix(self):
        sms = self._fresh_sms()
        captured_calls = []
        def capture(*args, **kwargs):
            captured_calls.append(args[0])
            return _run()
        with patch('subprocess.run', side_effect=capture):
            sms.send("+48123456789", "Short")
        # Single chunk — no [1/1] prefix
        assert "[1/1]" not in captured_calls[0][-1]
        assert "Short" in captured_calls[0][-1]


class TestSMSGetSimInfo:
    def _fresh_sms(self):
        if 'sensors.sms' in sys.modules:
            del sys.modules['sensors.sms']
        from sensors import sms
        return sms

    def test_returns_parsed_json(self):
        sms = self._fresh_sms()
        info = {"network_operator_name": "Play", "sim_state": "SIM_STATE_READY"}
        with patch('subprocess.run', return_value=_run(json.dumps(info))):
            result = sms.get_sim_info()
        assert result["network_operator_name"] == "Play"
        assert result["sim_state"] == "SIM_STATE_READY"

    def test_empty_output_returns_empty_dict(self):
        sms = self._fresh_sms()
        with patch('subprocess.run', return_value=_run("")):
            result = sms.get_sim_info()
        assert result == {}

    def test_subprocess_exception_returns_empty_dict(self):
        sms = self._fresh_sms()
        with patch('subprocess.run', side_effect=Exception("no termux")):
            result = sms.get_sim_info()
        assert result == {}

    def test_invalid_json_returns_empty_dict(self):
        sms = self._fresh_sms()
        with patch('subprocess.run', return_value=_run("not json")):
            result = sms.get_sim_info()
        assert result == {}


# ── Audio ──────────────────────────────────────────────────────────────────────

class TestAudioMeasureAmbientDb:
    def _fresh_audio(self):
        if 'sensors.audio' in sys.modules:
            del sys.modules['sensors.audio']
        from sensors import audio
        return audio

    def test_returns_float(self):
        audio = self._fresh_audio()
        with patch('subprocess.run', return_value=_run()):
            result = audio.measure_ambient_db()
        assert isinstance(result, float)

    def test_returns_minus_one_when_no_db_tool(self):
        audio = self._fresh_audio()
        with patch('subprocess.run', return_value=_run()):
            result = audio.measure_ambient_db()
        assert result == -1.0

    def test_subprocess_exception_returns_minus_one(self):
        audio = self._fresh_audio()
        with patch('subprocess.run', side_effect=Exception("microphone error")):
            result = audio.measure_ambient_db()
        assert result == -1.0

    def test_timeout_exception_returns_minus_one(self):
        import subprocess
        audio = self._fresh_audio()
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired(cmd="termux-microphone-record", timeout=5)):
            result = audio.measure_ambient_db()
        assert result == -1.0

    def test_custom_duration_ms(self):
        audio = self._fresh_audio()
        with patch('subprocess.run', return_value=_run()) as mock_run:
            result = audio.measure_ambient_db(duration_ms=2000)
        assert result == -1.0
        mock_run.assert_called_once()


class TestAudioDetectVoice:
    def _fresh_audio(self):
        if 'sensors.audio' in sys.modules:
            del sys.modules['sensors.audio']
        from sensors import audio
        return audio

    def test_returns_dict_with_required_keys(self):
        audio = self._fresh_audio()
        with patch('subprocess.run', return_value=_run()):
            with patch('pathlib.Path.exists', return_value=False):
                result = audio.detect_voice(duration_s=1)
        assert "voice_detected" in result
        assert "duration_s" in result

    def test_no_voice_when_file_missing(self):
        audio = self._fresh_audio()
        with patch('subprocess.run', return_value=_run()):
            with patch('pathlib.Path.exists', return_value=False):
                result = audio.detect_voice(duration_s=1)
        assert result["voice_detected"] is False
        assert result["file"] is None

    def test_no_voice_when_file_too_small(self):
        audio = self._fresh_audio()
        stat_mock = MagicMock()
        stat_mock.st_size = 5000  # less than 10000 threshold
        with patch('subprocess.run', return_value=_run()):
            with patch('pathlib.Path.exists', return_value=True):
                with patch('pathlib.Path.stat', return_value=stat_mock):
                    result = audio.detect_voice(duration_s=1)
        assert result["voice_detected"] is False

    def test_voice_detected_when_file_large_enough(self):
        audio = self._fresh_audio()
        stat_mock = MagicMock()
        stat_mock.st_size = 50000  # larger than 10000 threshold
        with patch('subprocess.run', return_value=_run()):
            with patch('pathlib.Path.exists', return_value=True):
                with patch('pathlib.Path.stat', return_value=stat_mock):
                    result = audio.detect_voice(duration_s=1)
        assert result["voice_detected"] is True
        assert result["file"] is not None

    def test_duration_preserved_in_result(self):
        audio = self._fresh_audio()
        with patch('subprocess.run', return_value=_run()):
            with patch('pathlib.Path.exists', return_value=False):
                result = audio.detect_voice(duration_s=5)
        assert result["duration_s"] == 5

    def test_subprocess_exception_returns_error_dict(self):
        audio = self._fresh_audio()
        with patch('subprocess.run', side_effect=Exception("microphone unavailable")):
            result = audio.detect_voice(duration_s=1)
        assert result["voice_detected"] is False
        assert "error" in result

    def test_timeout_exception_returns_error_dict(self):
        import subprocess
        audio = self._fresh_audio()
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired(cmd="termux-microphone-record", timeout=10)):
            result = audio.detect_voice(duration_s=1)
        assert result["voice_detected"] is False
        assert "error" in result

    def test_error_message_in_result(self):
        audio = self._fresh_audio()
        with patch('subprocess.run', side_effect=Exception("specific error message")):
            result = audio.detect_voice(duration_s=1)
        assert "specific error message" in result["error"]
