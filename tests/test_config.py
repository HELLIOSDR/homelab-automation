"""
tests/test_config.py — walidacja config.yaml
"""
import os
import yaml
import pytest

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "config.yaml")


@pytest.fixture(scope="module")
def config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_config_file_exists():
    """config.yaml musi istnieć."""
    assert os.path.isfile(CONFIG_PATH), f"Brak pliku konfiguracji: {CONFIG_PATH}"


def test_required_key_agent_name(config):
    """agent.name musi być zdefiniowane."""
    assert "agent" in config, "Brak sekcji 'agent' w config.yaml"
    assert "name" in config["agent"], "Brak klucza 'agent.name' w config.yaml"
    assert config["agent"]["name"], "agent.name nie może być pusty"


def test_required_key_agent_claude_model(config):
    """agent.claude_model musi być zdefiniowane."""
    assert "agent" in config, "Brak sekcji 'agent' w config.yaml"
    assert "claude_model" in config["agent"], "Brak klucza 'agent.claude_model' w config.yaml"
    assert config["agent"]["claude_model"], "agent.claude_model nie może być pusty"


def test_required_key_sensors(config):
    """Sekcja sensors musi istnieć."""
    assert "sensors" in config, "Brak sekcji 'sensors' w config.yaml"
    assert isinstance(config["sensors"], dict), "sensors musi być słownikiem"


def test_required_key_homelab(config):
    """Sekcja homelab musi istnieć."""
    assert "homelab" in config, "Brak sekcji 'homelab' w config.yaml"
    assert isinstance(config["homelab"], dict), "homelab musi być słownikiem"


def test_sensor_interval_positive(config):
    """agent.sensor_interval_s musi być > 0."""
    assert "agent" in config, "Brak sekcji 'agent' w config.yaml"
    assert "sensor_interval_s" in config["agent"], "Brak klucza 'agent.sensor_interval_s'"
    interval = config["agent"]["sensor_interval_s"]
    assert isinstance(interval, (int, float)), "sensor_interval_s musi być liczbą"
    assert interval > 0, f"sensor_interval_s musi być > 0, got: {interval}"


def test_api_port_in_valid_range(config):
    """agent.api_port musi być w zakresie 1024-65535."""
    assert "agent" in config, "Brak sekcji 'agent' w config.yaml"
    assert "api_port" in config["agent"], "Brak klucza 'agent.api_port'"
    port = config["agent"]["api_port"]
    assert isinstance(port, int), "api_port musi być liczbą całkowitą"
    assert 1024 <= port <= 65535, f"api_port musi być w zakresie 1024-65535, got: {port}"
