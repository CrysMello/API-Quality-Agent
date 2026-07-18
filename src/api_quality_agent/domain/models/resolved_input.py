from dataclasses import dataclass

from api_quality_agent.domain.models.input_origin import InputOrigin
from api_quality_agent.domain.policies import ensure_non_empty_id


@dataclass(frozen=True)
class ResolvedInput:
    origin: InputOrigin
    content_type: str
    name: str
    content: str

    def __post_init__(self) -> None:
        ensure_non_empty_id(self.content_type, "ResolvedInput.content_type")
        ensure_non_empty_id(self.name, "ResolvedInput.name")
