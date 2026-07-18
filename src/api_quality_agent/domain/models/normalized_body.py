from dataclasses import dataclass

from api_quality_agent.domain.models.body_mode import BodyMode


@dataclass(frozen=True)
class NormalizedBodyField:
    key: str | None
    value: str | None
    field_type: str | None
    disabled: bool = False


@dataclass(frozen=True)
class NormalizedBody:
    mode: BodyMode
    content_type: str | None
    has_content: bool
    text_content: str | None
    fields: tuple[NormalizedBodyField, ...]
    graphql_query: str | None
    variable_references: tuple[str, ...]
