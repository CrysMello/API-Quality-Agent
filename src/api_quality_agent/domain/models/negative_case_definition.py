from dataclasses import dataclass

from api_quality_agent.domain.models.negative_case_type import NegativeCaseType


@dataclass(frozen=True)
class NegativeCaseDefinition:
    case_type: NegativeCaseType
    field: str
    description: str
    evidence: str
