from dataclasses import dataclass

from api_quality_agent.domain.models.parameter import Parameter
from api_quality_agent.domain.models.request_definition import RequestDefinition
from api_quality_agent.domain.models.response_definition import ResponseDefinition
from api_quality_agent.domain.policies import ensure_non_empty_id


@dataclass(frozen=True)
class Endpoint:
    method: str
    path: str
    operation_id: str | None
    summary: str | None
    parameters: tuple[Parameter, ...]
    request: RequestDefinition | None
    responses: tuple[ResponseDefinition, ...]
    security_requirement_names: tuple[str, ...]

    def __post_init__(self) -> None:
        ensure_non_empty_id(self.method, "Endpoint.method")
        ensure_non_empty_id(self.path, "Endpoint.path")
