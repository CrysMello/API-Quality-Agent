from dataclasses import dataclass

from api_quality_agent.domain.models.auth_source import AuthSource
from api_quality_agent.domain.models.auth_type import AuthType


@dataclass(frozen=True)
class NormalizedAuth:
    auth_type: AuthType
    source: AuthSource
    variable_references: tuple[str, ...]
    has_sensitive_values: bool
    raw_type: str | None
