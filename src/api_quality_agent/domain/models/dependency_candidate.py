from dataclasses import dataclass

from api_quality_agent.domain.models.dependency_confidence import DependencyConfidence
from api_quality_agent.domain.models.dependency_evidence_type import DependencyEvidenceType


@dataclass(frozen=True)
class DependencyCandidate:
    source_endpoint: str
    target_endpoint: str
    confidence: DependencyConfidence
    evidence_type: DependencyEvidenceType
    description: str
