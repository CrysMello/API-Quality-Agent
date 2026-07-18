from dataclasses import dataclass
from typing import Any

from api_quality_agent.domain.models.postman_collection_items import CollectionEvent, CollectionItem
from api_quality_agent.domain.policies import ensure_non_empty_id


@dataclass(frozen=True)
class PostmanCollectionDocument:
    postman_id: str | None
    name: str
    description: str | None
    schema: str | None
    items: tuple[CollectionItem, ...]
    variables: tuple[dict[str, Any], ...]
    auth: dict[str, Any] | None
    events: tuple[CollectionEvent, ...]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        ensure_non_empty_id(self.name, "PostmanCollectionDocument.name")
