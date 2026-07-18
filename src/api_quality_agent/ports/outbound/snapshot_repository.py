from typing import Protocol, runtime_checkable

from api_quality_agent.domain.models import ContractSnapshot, SnapshotKey


@runtime_checkable
class SnapshotRepository(Protocol):
    def load_baseline(self, key: SnapshotKey) -> ContractSnapshot | None: ...

    def save_baseline(self, snapshot: ContractSnapshot, *, overwrite: bool = False) -> None: ...
