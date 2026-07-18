from pathlib import Path

from api_quality_agent.domain.models import ArtifactLocation, GeneratedArtifact
from api_quality_agent.domain.policies import ensure_non_empty_id

DEFAULT_ARTIFACTS_BASE_PATH = Path("artifacts")


class LocalArtifactRepository:
    def __init__(self, base_path: Path | None = None) -> None:
        self._base_path = base_path or DEFAULT_ARTIFACTS_BASE_PATH

    def save(
        self,
        *,
        workspace_id: str,
        collection_id: str,
        execution_id: str,
        artifact: GeneratedArtifact,
    ) -> ArtifactLocation:
        ensure_non_empty_id(workspace_id, "workspace_id")
        ensure_non_empty_id(collection_id, "collection_id")
        ensure_non_empty_id(execution_id, "execution_id")
        ensure_non_empty_id(artifact.relative_path, "artifact.relative_path")

        target_path = (
            self._base_path
            / workspace_id
            / collection_id
            / execution_id
            / artifact.category
            / artifact.relative_path
        )
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(artifact.content, encoding="utf-8")

        return ArtifactLocation(path=str(target_path))
