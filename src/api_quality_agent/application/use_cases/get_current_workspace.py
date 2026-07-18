from api_quality_agent.ports.outbound import SelectionRepository


class GetCurrentWorkspaceUseCase:
    def __init__(self, selection_repository: SelectionRepository) -> None:
        self._selection_repository = selection_repository

    def execute(self) -> str | None:
        return self._selection_repository.load().workspace_id
