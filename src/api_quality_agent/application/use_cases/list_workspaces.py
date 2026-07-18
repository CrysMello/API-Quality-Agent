from api_quality_agent.domain.models import WorkspaceRef
from api_quality_agent.ports.outbound import WorkspaceRepository


class ListWorkspacesUseCase:
    def __init__(self, workspace_repository: WorkspaceRepository) -> None:
        self._workspace_repository = workspace_repository

    def execute(self) -> tuple[WorkspaceRef, ...]:
        return self._workspace_repository.list()
