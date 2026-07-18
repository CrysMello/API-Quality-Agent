from dataclasses import dataclass
from typing import Any

from api_quality_agent.domain.models.parameter_location import ParameterLocation
from api_quality_agent.domain.policies import ensure_non_empty_id


@dataclass(frozen=True)
class Parameter:
    name: str
    location: ParameterLocation
    required: bool
    schema: dict[str, Any] | None
    description: str | None = None
    example: Any = None

    def __post_init__(self) -> None:
        ensure_non_empty_id(self.name, "Parameter.name")
