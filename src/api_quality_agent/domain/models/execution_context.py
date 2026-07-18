import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from api_quality_agent.domain.exceptions import InputError
from api_quality_agent.domain.models.execution_mode import ExecutionMode
from api_quality_agent.domain.policies import ensure_non_empty_id


def _default_id_factory() -> str:
    return str(uuid.uuid4())


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ExecutionContext:
    execution_id: str
    started_at: datetime
    mode: ExecutionMode
    source: str
    workspace_id: str | None = None
    workspace_name: str | None = None
    collection_id: str | None = None
    collection_name: str | None = None
    warnings: list[str] = field(default_factory=list)
    artifact_references: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        ensure_non_empty_id(self.execution_id, "ExecutionContext.execution_id")
        ensure_non_empty_id(self.source, "ExecutionContext.source")
        self.mode = self._coerce_mode(self.mode)
        if self.started_at.tzinfo is None:
            raise InputError("ExecutionContext.started_at deve ser timezone-aware.")
        if self.workspace_id is not None:
            ensure_non_empty_id(self.workspace_id, "ExecutionContext.workspace_id")
        if self.workspace_name is not None:
            ensure_non_empty_id(self.workspace_name, "ExecutionContext.workspace_name")
        if self.collection_id is not None:
            ensure_non_empty_id(self.collection_id, "ExecutionContext.collection_id")
        if self.collection_name is not None:
            ensure_non_empty_id(self.collection_name, "ExecutionContext.collection_name")

    @staticmethod
    def _coerce_mode(mode: "ExecutionMode | str") -> ExecutionMode:
        if isinstance(mode, ExecutionMode):
            return mode
        try:
            return ExecutionMode(mode)
        except ValueError as exc:
            raise InputError(f"ExecutionContext.mode inválido: {mode!r}") from exc

    @classmethod
    def create(
        cls,
        *,
        mode: "ExecutionMode | str",
        source: str,
        workspace_id: str | None = None,
        workspace_name: str | None = None,
        collection_id: str | None = None,
        collection_name: str | None = None,
        id_factory: Callable[[], str] = _default_id_factory,
        clock: Callable[[], datetime] = _default_clock,
    ) -> "ExecutionContext":
        return cls(
            execution_id=id_factory(),
            started_at=clock(),
            mode=cls._coerce_mode(mode),
            source=source,
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            collection_id=collection_id,
            collection_name=collection_name,
        )

    def add_warning(self, message: str) -> None:
        ensure_non_empty_id(message, "warning")
        self.warnings.append(message)

    def add_artifact_reference(self, reference: str) -> None:
        ensure_non_empty_id(reference, "artifact_reference")
        self.artifact_references.append(reference)

    def to_dict(self) -> dict[str, Any]:
        # Lista explícita de campos: garante que nenhum atributo futuro
        # (ex.: uma credencial adicionada por engano) vaze na serialização.
        return {
            "execution_id": self.execution_id,
            "started_at": self.started_at.isoformat(),
            "mode": self.mode.value,
            "source": self.source,
            "workspace_id": self.workspace_id,
            "workspace_name": self.workspace_name,
            "collection_id": self.collection_id,
            "collection_name": self.collection_name,
            "warnings": list(self.warnings),
            "artifact_references": list(self.artifact_references),
        }
