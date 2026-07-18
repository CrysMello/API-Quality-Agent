from dataclasses import dataclass

from api_quality_agent.domain.models.diff_category import DiffCategory
from api_quality_agent.domain.models.diff_change_type import DiffChangeType
from api_quality_agent.domain.models.diff_risk_level import DiffRiskLevel


@dataclass(frozen=True)
class DiffEntry:
    change_type: DiffChangeType
    category: DiffCategory
    target: str
    risk: DiffRiskLevel
    description: str
