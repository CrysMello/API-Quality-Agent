from typing import Protocol, runtime_checkable

from api_quality_agent.domain.models import ArtifactLocation, GeneratedArtifact


@runtime_checkable
class ArtifactRepository(Protocol):
    def save(
        self,
        *,
        workspace_id: str,
        collection_id: str,
        execution_id: str,
        artifact: GeneratedArtifact,
    ) -> ArtifactLocation: ...
