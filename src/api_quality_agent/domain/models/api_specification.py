from dataclasses import dataclass

from api_quality_agent.domain.models.api_specification_type import ApiSpecificationType
from api_quality_agent.domain.models.endpoint import Endpoint
from api_quality_agent.domain.models.security_definition import SecurityDefinition
from api_quality_agent.domain.policies import ensure_non_empty_id


@dataclass(frozen=True)
class ApiSpecification:
    spec_type: ApiSpecificationType
    spec_version: str
    title: str | None
    api_version: str | None
    servers: tuple[str, ...]
    endpoints: tuple[Endpoint, ...]
    security_schemes: tuple[SecurityDefinition, ...]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        ensure_non_empty_id(self.spec_version, "ApiSpecification.spec_version")
