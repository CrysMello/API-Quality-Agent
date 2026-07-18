from typing import Protocol, runtime_checkable

from api_quality_agent.domain.models import WorkspaceRef


@runtime_checkable
class WorkspaceRepository(Protocol):
    def list(self) -> tuple[WorkspaceRef, ...]: ...
