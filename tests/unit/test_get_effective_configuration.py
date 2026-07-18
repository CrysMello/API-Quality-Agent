from pathlib import Path

from api_quality_agent import __version__
from api_quality_agent.application.use_cases import get_effective_configuration


def test_reports_missing_api_key():
    configuration = get_effective_configuration(environment={}, working_directory=Path("."))
    assert configuration.postman_api_key_configured is False
    assert configuration.postman_api_key_masked is None


def test_masks_configured_api_key():
    fake_key = "P0STM4N-FAKE-KEY-1234567890"
    configuration = get_effective_configuration(
        environment={"POSTMAN_API_KEY": fake_key},
        working_directory=Path("."),
    )
    assert configuration.postman_api_key_configured is True
    assert configuration.postman_api_key_masked is not None
    assert fake_key not in configuration.postman_api_key_masked


def test_reports_package_version():
    configuration = get_effective_configuration(environment={}, working_directory=Path("."))
    assert configuration.package_version == __version__
