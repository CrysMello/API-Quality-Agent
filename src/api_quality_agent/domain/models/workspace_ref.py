from dataclasses import dataclass

from api_quality_agent.domain.policies import ensure_non_empty_id


@dataclass(frozen=True)
class WorkspaceRef:
    id: str
    name: str

    def __post_init__(self) -> None:
        ensure_non_empty_id(self.id, "WorkspaceRef.id")
        ensure_non_empty_id(self.name, "WorkspaceRef.name")
