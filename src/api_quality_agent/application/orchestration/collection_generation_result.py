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
    PostmanCollectionDocument,
)


@dataclass(frozen=True)
class CollectionGenerationResult:
    execution_context: ExecutionContext
    analysis_warnings: tuple[AnalysisWarning, ...]
    dependencies: tuple[DependencyCandidate, ...]
    endpoint_outcomes: tuple[EndpointGenerationOutcome, ...]
    diff: DiffResult
    # Documentos completos (original e com blocos gerenciados aplicados em
    # cópia), preservados para permitirem a atualização remota segura em uma
    # etapa posterior sem precisar reprocessar ou reobter a Collection.
    original_document: PostmanCollectionDocument
    modified_document: PostmanCollectionDocument
    artifact_locations: tuple[ArtifactLocation, ...] = ()
