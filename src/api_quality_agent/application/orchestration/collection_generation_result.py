from dataclasses import dataclass

from api_quality_agent.application.orchestration.endpoint_generation_outcome import (
    EndpointGenerationOutcome,
)
from api_quality_agent.domain.models import (
    AnalysisWarning,
    ArtifactLocation,
    DependencyCandidate,
    DiffResult,
    ExecutionContext,
)


@dataclass(frozen=True)
class CollectionGenerationResult:
    execution_context: ExecutionContext
    analysis_warnings: tuple[AnalysisWarning, ...]
    dependencies: tuple[DependencyCandidate, ...]
    endpoint_outcomes: tuple[EndpointGenerationOutcome, ...]
    diff: DiffResult
    artifact_locations: tuple[ArtifactLocation, ...] = ()
