from dataclasses import dataclass

from api_quality_agent.domain.policies import ensure_non_empty_id


@dataclass(frozen=True)
class SnapshotKey:
    workspace_id: str
    collection_id: str
    method: str
    endpoint: str

    def __post_init__(self) -> None:
        ensure_non_empty_id(self.workspace_id, "SnapshotKey.workspace_id")
        ensure_non_empty_id(self.collection_id, "SnapshotKey.collection_id")
        ensure_non_empty_id(self.method, "SnapshotKey.method")
        ensure_non_empty_id(self.endpoint, "SnapshotKey.endpoint")
