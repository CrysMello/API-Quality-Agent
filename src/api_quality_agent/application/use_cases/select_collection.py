from api_quality_agent.domain.exceptions import InputError
from api_quality_agent.domain.models import ActiveSelection, CollectionRef
from api_quality_agent.domain.services import CollectionSelectionService
from api_quality_agent.ports.outbound import SelectionRepository


class SelectCollectionUseCase:
    def __init__(
        self,
        selection_service: CollectionSelectionService,
        selection_repository: SelectionRepository,
    ) -> None:
        self._selection_service = selection_service
        self._selection_repository = selection_repository

    def execute(
        self,
        *,
        collection_id: str | None = None,
        collection_name: str | None = None,
    ) -> CollectionRef:
        current_selection = self._selection_repository.load()
        workspace_id = current_selection.workspace_id
        if not workspace_id:
            raise InputError(
                "Nenhum Workspace ativo. Selecione um Workspace antes de escolher uma Collection."
            )

        selected = self._selection_service.resolve(
            workspace_id=workspace_id,
            collection_id=collection_id,
            collection_name=collection_name,
        )

        self._selection_repository.save(
            ActiveSelection(workspace_id=workspace_id, collection_id=selected.id)
        )
        return selected
