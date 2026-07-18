from dataclasses import dataclass

from api_quality_agent.domain.policies import ensure_non_empty_id


@dataclass(frozen=True)
class ActiveSelection:
    workspace_id: str | None = None
    collection_id: str | None = None

    def __post_init__(self) -> None:
        if self.workspace_id is not None:
            ensure_non_empty_id(self.workspace_id, "ActiveSelection.workspace_id")
        if self.collection_id is not None:
            ensure_non_empty_id(self.collection_id, "ActiveSelection.collection_id")
