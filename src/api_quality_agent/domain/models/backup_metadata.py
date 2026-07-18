from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class BackupMetadata:
    collection_id: str
    created_at_utc: datetime
    sha256: str
    size_bytes: int
    contains_sensitive_data: bool
    backup_path: Path
