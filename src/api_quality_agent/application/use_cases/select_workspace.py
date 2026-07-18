from api_quality_agent.domain.exceptions import (
    AmbiguousResourceError,
    InputError,
    ResourceNotFoundError,
)
from api_quality_agent.domain.models import ActiveSelection, WorkspaceRef
from api_quality_agent.ports.outbound import SelectionRepository, WorkspaceRepository


class SelectWorkspaceUseCase:
    def __init__(
        self,
        workspace_repository: WorkspaceRepository,
        selection_repository: SelectionRepository,
    ) -> None:
        self._workspace_repository = workspace_repository
        self._selection_repository = selection_repository

    def execute(
        self,
        *,
        workspace_id: str | None = None,
        workspace_name: str | None = None,
    ) -> WorkspaceRef:
        if not workspace_id and not workspace_name:
            raise InputError(
                "Informe o ID ou o nome do Workspace a selecionar; "
                "nenhum Workspace é selecionado automaticamente."
            )

        workspaces = self._workspace_repository.list()
        selected = _resolve_workspace(workspaces, workspace_id, workspace_name)

        current_selection = self._selection_repository.load()
        if current_selection.workspace_id == selected.id:
            # Mesmo Workspace de antes: nada no contexto muda, preserva a Collection ativa.
            new_selection = current_selection
        else:
            # Novo Workspace: a Collection ativa pertencia ao contexto anterior.
            new_selection = ActiveSelection(workspace_id=selected.id, collection_id=None)

        self._selection_repository.save(new_selection)
        return selected


def _resolve_workspace(
    workspaces: tuple[WorkspaceRef, ...],
    workspace_id: str | None,
    workspace_name: str | None,
) -> WorkspaceRef:
    if workspace_id:
        match = next((workspace for workspace in workspaces if workspace.id == workspace_id), None)
        if match is None:
            raise ResourceNotFoundError(f"Workspace com ID '{workspace_id}' não encontrado.")
        return match

    matches = [workspace for workspace in workspaces if workspace.name == workspace_name]
    if not matches:
        raise ResourceNotFoundError(f"Workspace com nome '{workspace_name}' não encontrado.")
    if len(matches) > 1:
        raise AmbiguousResourceError(
            f"Múltiplos Workspaces encontrados com o nome '{workspace_name}'. "
            "Utilize o ID para selecionar um deles."
        )
    return matches[0]
