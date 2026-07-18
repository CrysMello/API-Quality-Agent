from dataclasses import dataclass

from api_quality_agent.domain.models.analysis_warning import AnalysisWarning
from api_quality_agent.domain.models.dependency_candidate import DependencyCandidate
from api_quality_agent.domain.models.endpoint_analysis import EndpointAnalysis


@dataclass(frozen=True)
class ApiAnalysisResult:
    source_type: str
    endpoints: tuple[EndpointAnalysis, ...]
    dependencies: tuple[DependencyCandidate, ...]
    warnings: tuple[AnalysisWarning, ...]
