from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BackupPolicy:
    enabled: bool = True
    directory: Path = Path("backups")
    max_backups_per_collection: int | None = None
    max_age_days: int | None = None
