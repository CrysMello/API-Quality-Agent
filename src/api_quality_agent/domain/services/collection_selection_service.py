from api_quality_agent.domain.exceptions import (
    AmbiguousResourceError,
    InputError,
    ResourceNotFoundError,
)
from api_quality_agent.domain.models import CollectionRef
from api_quality_agent.ports.outbound import CollectionRepository


class CollectionSelectionService:
    def __init__(self, collection_repository: CollectionRepository) -> None:
        self._collection_repository = collection_repository

    def resolve(
        self,
        *,
        workspace_id: str,
        collection_id: str | None = None,
        collection_name: str | None = None,
    ) -> CollectionRef:
        if not collection_id and not collection_name:
            raise InputError("Informe o ID ou o nome da Collection a selecionar.")

        # A lista já é restrita ao Workspace informado: um ID de Collection de
        # outro Workspace nunca aparece aqui, então o vínculo é validado
        # naturalmente (nunca aceito por engano uma Collection incompatível).
        collections = self._collection_repository.list(workspace_id)

        if collection_id:
            match = next((c for c in collections if c.id == collection_id), None)
            if match is None:
                raise ResourceNotFoundError(
                    f"Collection com ID '{collection_id}' não encontrada ou inacessível "
                    f"no Workspace '{workspace_id}'."
                )
            return match

        matches = [c for c in collections if c.name == collection_name]
        if not matches:
            raise ResourceNotFoundError(
                f"Collection com nome '{collection_name}' não encontrada no "
                f"Workspace '{workspace_id}'."
            )
        if len(matches) > 1:
            raise AmbiguousResourceError(
                f"Múltiplas Collections encontradas com o nome '{collection_name}' "
                f"no Workspace '{workspace_id}'. Utilize o ID para selecionar uma delas."
            )
        return matches[0]
