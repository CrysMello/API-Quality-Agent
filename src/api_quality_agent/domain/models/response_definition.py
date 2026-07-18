from dataclasses import dataclass

from api_quality_agent.domain.models.media_type_definition import MediaTypeDefinition
from api_quality_agent.domain.policies import ensure_non_empty_id


@dataclass(frozen=True)
class ResponseDefinition:
    status_code: str
    description: str | None
    media_types: tuple[MediaTypeDefinition, ...]

    def __post_init__(self) -> None:
        ensure_non_empty_id(self.status_code, "ResponseDefinition.status_code")
