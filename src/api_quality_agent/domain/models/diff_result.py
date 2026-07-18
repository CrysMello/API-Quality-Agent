from dataclasses import dataclass

from api_quality_agent.domain.models.diff_change_type import DiffChangeType
from api_quality_agent.domain.models.diff_entry import DiffEntry
from api_quality_agent.domain.models.diff_risk_level import DiffRiskLevel


@dataclass(frozen=True)
class DiffResult:
    entries: tuple[DiffEntry, ...]

    @property
    def has_changes(self) -> bool:
        return bool(self.entries)

    @property
    def has_removals(self) -> bool:
        return any(entry.change_type == DiffChangeType.REMOVED for entry in self.entries)

    @property
    def has_high_risk_changes(self) -> bool:
        return any(entry.risk == DiffRiskLevel.HIGH for entry in self.entries)
