from dataclasses import dataclass
from typing import Any

from api_quality_agent.domain.policies import ensure_non_empty_id


@dataclass(frozen=True)
class MediaTypeDefinition:
    content_type: str
    schema: dict[str, Any] | None
    example: Any = None

    def __post_init__(self) -> None:
        ensure_non_empty_id(self.content_type, "MediaTypeDefinition.content_type")
