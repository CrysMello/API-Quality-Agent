import os
from dataclasses import dataclass
from pathlib import Path

from api_quality_agent import __version__
from api_quality_agent.shared import mask_secret

POSTMAN_API_KEY_ENV_VAR = "POSTMAN_API_KEY"


@dataclass(frozen=True)
class EffectiveConfiguration:
    package_version: str
    working_directory: str
    postman_api_key_configured: bool
    postman_api_key_masked: str | None


def get_effective_configuration(
    *,
    environment: dict[str, str] | None = None,
    working_directory: Path | None = None,
) -> EffectiveConfiguration:
    env = environment if environment is not None else os.environ
    cwd = working_directory if working_directory is not None else Path.cwd()
    raw_api_key = env.get(POSTMAN_API_KEY_ENV_VAR)
    configured = bool(raw_api_key)
    return EffectiveConfiguration(
        package_version=__version__,
        working_directory=str(cwd),
        postman_api_key_configured=configured,
        postman_api_key_masked=mask_secret(raw_api_key) if raw_api_key else None,
    )
