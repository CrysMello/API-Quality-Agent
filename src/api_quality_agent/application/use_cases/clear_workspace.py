from api_quality_agent.domain.models import ActiveSelection
from api_quality_agent.ports.outbound import SelectionRepository


class ClearWorkspaceUseCase:
    def __init__(self, selection_repository: SelectionRepository) -> None:
        self._selection_repository = selection_repository

    def execute(self) -> None:
        # A Collection ativa depende do contexto do Workspace: limpar um
        # implica limpar o outro, evitando referenciar um contexto órfão.
        self._selection_repository.save(ActiveSelection(workspace_id=None, collection_id=None))
