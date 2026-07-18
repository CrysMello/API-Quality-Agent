from api_quality_agent.domain.models import ActiveSelection
from api_quality_agent.ports.outbound import SelectionRepository


class ClearCollectionUseCase:
    def __init__(self, selection_repository: SelectionRepository) -> None:
        self._selection_repository = selection_repository

    def execute(self) -> None:
        current_selection = self._selection_repository.load()
        # Diferente de limpar o Workspace, limpar a Collection preserva o
        # Workspace ativo: ele continua fazendo sentido por si só.
        self._selection_repository.save(
            ActiveSelection(workspace_id=current_selection.workspace_id, collection_id=None)
        )
