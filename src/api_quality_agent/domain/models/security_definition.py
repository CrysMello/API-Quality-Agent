from dataclasses import dataclass

from api_quality_agent.domain.policies import ensure_non_empty_id


@dataclass(frozen=True)
class SecurityDefinition:
    name: str
    type: str
    scheme: str | None = None
    location: str | None = None
    parameter_name: str | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        ensure_non_empty_id(self.name, "SecurityDefinition.name")
        ensure_non_empty_id(self.type, "SecurityDefinition.type")
