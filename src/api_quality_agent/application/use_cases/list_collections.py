from api_quality_agent.domain.exceptions import InputError
from api_quality_agent.domain.models import CollectionRef
from api_quality_agent.ports.outbound import CollectionRepository, SelectionRepository


class ListCollectionsUseCase:
    def __init__(
        self,
        collection_repository: CollectionRepository,
        selection_repository: SelectionRepository,
    ) -> None:
        self._collection_repository = collection_repository
        self._selection_repository = selection_repository

    def execute(self) -> tuple[CollectionRef, ...]:
        workspace_id = self._selection_repository.load().workspace_id
        if not workspace_id:
            raise InputError(
                "Nenhum Workspace ativo. Selecione um Workspace antes de listar Collections."
            )
        return self._collection_repository.list(workspace_id)
