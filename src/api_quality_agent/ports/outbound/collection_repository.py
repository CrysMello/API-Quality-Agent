from typing import Protocol, runtime_checkable

from api_quality_agent.domain.models import CollectionRef, PostmanCollectionDocument


@runtime_checkable
class CollectionRepository(Protocol):
    def list(self, workspace_id: str) -> tuple[CollectionRef, ...]: ...

    def get(self, collection_id: str) -> PostmanCollectionDocument: ...
