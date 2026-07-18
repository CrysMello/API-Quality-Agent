from dataclasses import dataclass

from api_quality_agent.domain.models.parameter_analysis import ParameterAnalysis


@dataclass(frozen=True)
class EndpointAnalysis:
    source: str
    method: str | None
    path: str | None
    operation_id: str | None
    parameters: tuple[ParameterAnalysis, ...]
    has_request_body: bool
    request_content_types: tuple[str, ...]
    response_status_codes: tuple[str, ...]
    response_content_types: tuple[str, ...]
    auth_type: str | None
    variables_used: tuple[str, ...]
    has_examples: bool
    example_count: int
