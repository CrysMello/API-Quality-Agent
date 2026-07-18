from pathlib import Path
from typing import Protocol, runtime_checkable

from api_quality_agent.domain.models import BackupMetadata, BackupPolicy


@runtime_checkable
class BackupRepository(Protocol):
    def save(
        self,
        *,
        collection_id: str,
        workspace_id: str | None,
        content: bytes,
        contains_sensitive_data: bool,
    ) -> BackupMetadata: ...

    def verify(self, backup_path: Path, expected_sha256: str) -> bool: ...

    def apply_retention(
        self,
        *,
        collection_id: str,
        workspace_id: str | None,
        policy: BackupPolicy,
        keep_path: Path,
    ) -> None: ...
