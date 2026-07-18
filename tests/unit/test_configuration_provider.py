import pytest

from api_quality_agent.adapters.config import ConfigurationProvider
from api_quality_agent.domain.exceptions import ConfigurationError


def test_precedence_overrides_beat_everything():
    provider = ConfigurationProvider(
        overrides={"timeout": "override"},
        environment={"timeout": "env"},
        file_values={"timeout": "file"},
        defaults={"timeout": "default"},
    )
    assert provider.get("timeout") == "override"


def test_precedence_env_beats_file_and_defaults():
    provider = ConfigurationProvider(
        environment={"timeout": "env"},
        file_values={"timeout": "file"},
        defaults={"timeout": "default"},
    )
    assert provider.get("timeout") == "env"


def test_precedence_file_beats_defaults():
    provider = ConfigurationProvider(
        environment={},
        file_values={"timeout": "file"},
        defaults={"timeout": "default"},
    )
    assert provider.get("timeout") == "file"


def test_precedence_falls_back_to_defaults():
    provider = ConfigurationProvider(environment={}, file_values={}, defaults={"timeout": "default"})
    assert provider.get("timeout") == "default"


def test_missing_key_without_default_raises_configuration_error():
    provider = ConfigurationProvider(environment={}, file_values={}, defaults={})
    with pytest.raises(ConfigurationError):
        provider.get("missing")


def test_get_accepts_explicit_default_argument():
    provider = ConfigurationProvider(environment={}, file_values={}, defaults={})
    assert provider.get("missing", "fallback") == "fallback"


def test_require_rejects_blank_value():
    provider = ConfigurationProvider(overrides={"name": "   "})
    with pytest.raises(ConfigurationError):
        provider.require("name")


def test_require_returns_valid_value():
    provider = ConfigurationProvider(overrides={"name": "valor"})
    assert provider.require("name") == "valor"


def test_invalid_config_file_raises_configuration_error(tmp_path):
    invalid_file = tmp_path / "config.json"
    invalid_file.write_text("not-json", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        ConfigurationProvider(environment={}, config_file_path=invalid_file)


def test_config_file_values_are_loaded(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text('{"timeout": "from-file"}', encoding="utf-8")
    provider = ConfigurationProvider(environment={}, config_file_path=config_file)
    assert provider.get("timeout") == "from-file"


def test_missing_config_file_is_treated_as_empty(tmp_path):
    missing_file = tmp_path / "does-not-exist.json"
    provider = ConfigurationProvider(
        environment={}, config_file_path=missing_file, defaults={"timeout": "default"}
    )
    assert provider.get("timeout") == "default"
