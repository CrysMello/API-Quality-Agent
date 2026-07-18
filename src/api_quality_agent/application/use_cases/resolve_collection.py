from collections.abc import Callable

from api_quality_agent.domain.exceptions import InputError, ResourceNotFoundError
from api_quality_agent.domain.models import CollectionRef
from api_quality_agent.domain.services import CollectionSelectionService
from api_quality_agent.ports.outbound import CollectionRepository, SelectionRepository

InteractiveResolver = Callable[[tuple[CollectionRef, ...]], CollectionRef]


class ResolveCollectionUseCase:
    def __init__(
        self,
        selection_service: CollectionSelectionService,
        collection_repository: CollectionRepository,
        selection_repository: SelectionRepository,
    ) -> None:
        self._selection_service = selection_service
        self._collection_repository = collection_repository
        self._selection_repository = selection_repository

    def execute(
        self,
        *,
        collection_id: str | None = None,
        collection_name: str | None = None,
        allow_interactive: bool = False,
        interactive_resolver: InteractiveResolver | None = None,
    ) -> CollectionRef:
        workspace_id = self._selection_repository.load().workspace_id
        if not workspace_id:
            raise InputError(
                "Nenhum Workspace ativo. Selecione um Workspace antes de resolver uma Collection."
            )

        # 1. collection_id informado na execução
        if collection_id:
            return self._selection_service.resolve(
                workspace_id=workspace_id, collection_id=collection_id
            )

        # 2. collection_name informado na execução
        if collection_name:
            return self._selection_service.resolve(
                workspace_id=workspace_id, collection_name=collection_name
            )

        # 3. Collection ativa persistida (validada contra o Workspace atual)
        persisted_collection_id = self._selection_repository.load().collection_id
        if persisted_collection_id:
            collections = self._collection_repository.list(workspace_id)
            match = next((c for c in collections if c.id == persisted_collection_id), None)
            if match is not None:
                return match

        # 4. seleção interativa, somente quando explicitamente permitida
        if allow_interactive and interactive_resolver is not None:
            collections = self._collection_repository.list(workspace_id)
            return interactive_resolver(collections)

        # 5. erro orientado — nunca escolhe uma Collection silenciosamente
        raise ResourceNotFoundError(
            "Nenhuma Collection foi informada e não há Collection ativa válida para este "
            "Workspace. Informe o ID ou o nome da Collection, selecione uma Collection ativa "
            "com 'collection select', ou habilite a seleção interativa."
        )
