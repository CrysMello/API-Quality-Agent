from dataclasses import dataclass

from api_quality_agent.domain.policies import ensure_non_empty_id


@dataclass(frozen=True)
class CollectionRef:
    id: str
    name: str
    workspace_id: str

    def __post_init__(self) -> None:
        ensure_non_empty_id(self.id, "CollectionRef.id")
        ensure_non_empty_id(self.name, "CollectionRef.name")
        ensure_non_empty_id(self.workspace_id, "CollectionRef.workspace_id")
