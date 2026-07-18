import pytest

from api_quality_agent.application.use_cases import (
    ClearWorkspaceUseCase,
    GetCurrentWorkspaceUseCase,
    ListWorkspacesUseCase,
    SelectWorkspaceUseCase,
)
from api_quality_agent.domain.exceptions import (
    AmbiguousResourceError,
    InputError,
    ResourceNotFoundError,
)
from api_quality_agent.domain.models import ActiveSelection, WorkspaceRef


class _FakeWorkspaceRepository:
    def __init__(self, workspaces: tuple[WorkspaceRef, ...]) -> None:
        self._workspaces = workspaces

    def list(self) -> tuple[WorkspaceRef, ...]:
        return self._workspaces


class _InMemorySelectionRepository:
    def __init__(self, initial: ActiveSelection | None = None) -> None:
        self._selection = initial or ActiveSelection()

    def load(self) -> ActiveSelection:
        return self._selection

    def save(self, selection: ActiveSelection) -> None:
        self._selection = selection


_WORKSPACES = (
    WorkspaceRef(id="ws-1", name="Time A"),
    WorkspaceRef(id="ws-2", name="Time B"),
    WorkspaceRef(id="ws-3", name="Time B"),
)


# --- Listagem ------------------------------------------------------------------


def test_list_workspaces_delegates_to_repository():
    use_case = ListWorkspacesUseCase(_FakeWorkspaceRepository(_WORKSPACES))

    result = use_case.execute()

    assert result == _WORKSPACES


# --- Seleção por ID ---------------------------------------------------------------


def test_select_workspace_by_id_persists_selection():
    workspace_repository = _FakeWorkspaceRepository(_WORKSPACES)
    selection_repository = _InMemorySelectionRepository()
    use_case = SelectWorkspaceUseCase(workspace_repository, selection_repository)

    selected = use_case.execute(workspace_id="ws-1")

    assert selected == WorkspaceRef(id="ws-1", name="Time A")
    assert selection_repository.load().workspace_id == "ws-1"


def test_select_workspace_requires_id_or_name():
    use_case = SelectWorkspaceUseCase(
        _FakeWorkspaceRepository(_WORKSPACES), _InMemorySelectionRepository()
    )

    with pytest.raises(InputError):
        use_case.execute()


def test_select_workspace_by_id_takes_priority_over_name():
    workspace_repository = _FakeWorkspaceRepository(_WORKSPACES)
    selection_repository = _InMemorySelectionRepository()
    use_case = SelectWorkspaceUseCase(workspace_repository, selection_repository)

    # nome ambíguo ("Time B") seria rejeitado sozinho, mas o ID tem prioridade
    selected = use_case.execute(workspace_id="ws-2", workspace_name="Time B")

    assert selected.id == "ws-2"


# --- Seleção por nome único --------------------------------------------------------


def test_select_workspace_by_unique_name_succeeds():
    workspace_repository = _FakeWorkspaceRepository(_WORKSPACES)
    selection_repository = _InMemorySelectionRepository()
    use_case = SelectWorkspaceUseCase(workspace_repository, selection_repository)

    selected = use_case.execute(workspace_name="Time A")

    assert selected == WorkspaceRef(id="ws-1", name="Time A")
    assert selection_repository.load().workspace_id == "ws-1"


# --- Nome duplicado -----------------------------------------------------------------


def test_select_workspace_by_duplicated_name_raises_ambiguous_error():
    use_case = SelectWorkspaceUseCase(
        _FakeWorkspaceRepository(_WORKSPACES), _InMemorySelectionRepository()
    )

    with pytest.raises(AmbiguousResourceError):
        use_case.execute(workspace_name="Time B")


def test_ambiguous_name_does_not_select_anything_silently():
    selection_repository = _InMemorySelectionRepository()
    use_case = SelectWorkspaceUseCase(_FakeWorkspaceRepository(_WORKSPACES), selection_repository)

    with pytest.raises(AmbiguousResourceError):
        use_case.execute(workspace_name="Time B")

    assert selection_repository.load().workspace_id is None


# --- ID inexistente ------------------------------------------------------------------


def test_select_workspace_by_unknown_id_raises_not_found():
    selection_repository = _InMemorySelectionRepository()
    use_case = SelectWorkspaceUseCase(_FakeWorkspaceRepository(_WORKSPACES), selection_repository)

    with pytest.raises(ResourceNotFoundError):
        use_case.execute(workspace_id="ws-does-not-exist")

    assert selection_repository.load().workspace_id is None


def test_select_workspace_by_unknown_name_raises_not_found():
    use_case = SelectWorkspaceUseCase(
        _FakeWorkspaceRepository(_WORKSPACES), _InMemorySelectionRepository()
    )

    with pytest.raises(ResourceNotFoundError):
        use_case.execute(workspace_name="Time Inexistente")


# --- Current -------------------------------------------------------------------------


def test_get_current_workspace_returns_none_when_nothing_selected():
    use_case = GetCurrentWorkspaceUseCase(_InMemorySelectionRepository())

    assert use_case.execute() is None


def test_get_current_workspace_returns_persisted_id():
    selection_repository = _InMemorySelectionRepository(ActiveSelection(workspace_id="ws-2"))
    use_case = GetCurrentWorkspaceUseCase(selection_repository)

    assert use_case.execute() == "ws-2"


# --- Clear -----------------------------------------------------------------------------


def test_clear_workspace_resets_selection():
    selection_repository = _InMemorySelectionRepository(
        ActiveSelection(workspace_id="ws-1", collection_id="col-1")
    )
    use_case = ClearWorkspaceUseCase(selection_repository)

    use_case.execute()

    assert selection_repository.load() == ActiveSelection(workspace_id=None, collection_id=None)


# --- Invalidação da Collection --------------------------------------------------------


def test_clear_workspace_also_invalidates_active_collection():
    selection_repository = _InMemorySelectionRepository(
        ActiveSelection(workspace_id="ws-1", collection_id="col-1")
    )

    ClearWorkspaceUseCase(selection_repository).execute()

    selection = selection_repository.load()
    assert selection.workspace_id is None
    assert selection.collection_id is None


def test_selecting_a_different_workspace_invalidates_active_collection():
    selection_repository = _InMemorySelectionRepository(
        ActiveSelection(workspace_id="ws-1", collection_id="col-1")
    )
    use_case = SelectWorkspaceUseCase(_FakeWorkspaceRepository(_WORKSPACES), selection_repository)

    use_case.execute(workspace_id="ws-2")

    selection = selection_repository.load()
    assert selection.workspace_id == "ws-2"
    assert selection.collection_id is None


def test_reselecting_the_same_workspace_preserves_active_collection():
    selection_repository = _InMemorySelectionRepository(
        ActiveSelection(workspace_id="ws-1", collection_id="col-1")
    )
    use_case = SelectWorkspaceUseCase(_FakeWorkspaceRepository(_WORKSPACES), selection_repository)

    use_case.execute(workspace_id="ws-1")

    selection = selection_repository.load()
    assert selection.workspace_id == "ws-1"
    assert selection.collection_id == "col-1"
