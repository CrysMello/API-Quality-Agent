from dataclasses import dataclass

from api_quality_agent.domain.models.media_type_definition import MediaTypeDefinition


@dataclass(frozen=True)
class RequestDefinition:
    required: bool
    description: str | None
    media_types: tuple[MediaTypeDefinition, ...]
