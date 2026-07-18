from dataclasses import dataclass

from api_quality_agent.domain.models.change_severity import ChangeSeverity
from api_quality_agent.domain.models.contract_change_type import ContractChangeType


@dataclass(frozen=True)
class ContractChange:
    change_type: ContractChangeType
    severity: ChangeSeverity
    field_path: str
    description: str
