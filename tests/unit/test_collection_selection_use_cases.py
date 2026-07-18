import pytest

from api_quality_agent.application.use_cases import (
    ClearCollectionUseCase,
    GetCurrentCollectionUseCase,
    ListCollectionsUseCase,
    ResolveCollectionUseCase,
    SelectCollectionUseCase,
)
from api_quality_agent.domain.exceptions import (
    AmbiguousResourceError,
    InputError,
    ResourceNotFoundError,
)
from api_quality_agent.domain.models import ActiveSelection, CollectionRef
from api_quality_agent.domain.services import CollectionSelectionService


class _FakeCollectionRepository:
    def __init__(self, by_workspace: dict[str, tuple[CollectionRef, ...]]) -> None:
        self._by_workspace = by_workspace
        self.list_calls: list[str] = []

    def list(self, workspace_id: str) -> tuple[CollectionRef, ...]:
        self.list_calls.append(workspace_id)
        return self._by_workspace.get(workspace_id, ())

    def get(self, collection_id: str):  # pragma: no cover - não usado nesta etapa
        raise NotImplementedError


class _InMemorySelectionRepository:
    def __init__(self, initial: ActiveSelection | None = None) -> None:
        self._selection = initial or ActiveSelection()

    def load(self) -> ActiveSelection:
        return self._selection

    def save(self, selection: ActiveSelection) -> None:
        self._selection = selection


_COLLECTIONS_WS1 = (
    CollectionRef(id="c1", name="Collection A", workspace_id="ws-1"),
    CollectionRef(id="c2", name="Collection B", workspace_id="ws-1"),
    CollectionRef(id="c3", name="Collection B", workspace_id="ws-1"),
)
_COLLECTIONS_WS2 = (CollectionRef(id="c99", name="Outra Collection", workspace_id="ws-2"),)


def _make_repos(*, workspace_id: str | None = "ws-1"):
    collection_repository = _FakeCollectionRepository(
        {"ws-1": _COLLECTIONS_WS1, "ws-2": _COLLECTIONS_WS2}
    )
    selection_repository = _InMemorySelectionRepository(
        ActiveSelection(workspace_id=workspace_id) if workspace_id else None
    )
    selection_service = CollectionSelectionService(collection_repository)
    return collection_repository, selection_repository, selection_service


# --- Lista no Workspace ativo -------------------------------------------------------


def test_list_collections_in_active_workspace():
    collection_repository, selection_repository, _ = _make_repos()
    use_case = ListCollectionsUseCase(collection_repository, selection_repository)

    result = use_case.execute()

    assert result == _COLLECTIONS_WS1


# --- Sem Workspace -------------------------------------------------------------------


def test_list_collections_without_active_workspace_raises_input_error():
    collection_repository, selection_repository, _ = _make_repos(workspace_id=None)
    use_case = ListCollectionsUseCase(collection_repository, selection_repository)

    with pytest.raises(InputError):
        use_case.execute()


def test_select_collection_without_active_workspace_raises_input_error():
    _, selection_repository, selection_service = _make_repos(workspace_id=None)
    use_case = SelectCollectionUseCase(selection_service, selection_repository)

    with pytest.raises(InputError):
        use_case.execute(collection_id="c1")


def test_resolve_collection_without_active_workspace_raises_input_error():
    collection_repository, selection_repository, selection_service = _make_repos(
        workspace_id=None
    )
    use_case = ResolveCollectionUseCase(
        selection_service, collection_repository, selection_repository
    )

    with pytest.raises(InputError):
        use_case.execute()


# --- Seleção por ID ---------------------------------------------------------------


def test_select_collection_by_id_persists_selection():
    _, selection_repository, selection_service = _make_repos()
    use_case = SelectCollectionUseCase(selection_service, selection_repository)

    selected = use_case.execute(collection_id="c1")

    assert selected == CollectionRef(id="c1", name="Collection A", workspace_id="ws-1")
    assert selection_repository.load() == ActiveSelection(workspace_id="ws-1", collection_id="c1")


# --- Seleção por nome --------------------------------------------------------------


def test_select_collection_by_unique_name_persists_selection():
    _, selection_repository, selection_service = _make_repos()
    use_case = SelectCollectionUseCase(selection_service, selection_repository)

    selected = use_case.execute(collection_name="Collection A")

    assert selected.id == "c1"
    assert selection_repository.load().collection_id == "c1"


# --- Nome duplicado -----------------------------------------------------------------


def test_select_collection_by_duplicated_name_raises_ambiguous_error():
    _, selection_repository, selection_service = _make_repos()
    use_case = SelectCollectionUseCase(selection_service, selection_repository)

    with pytest.raises(AmbiguousResourceError):
        use_case.execute(collection_name="Collection B")

    # nenhuma seleção silenciosa: a ativa permanece intocada
    assert selection_repository.load().collection_id is None


# --- Alternância entre duas Collections --------------------------------------------


def test_switching_between_two_collections_updates_active_selection():
    _, selection_repository, selection_service = _make_repos()
    use_case = SelectCollectionUseCase(selection_service, selection_repository)

    use_case.execute(collection_id="c1")
    assert selection_repository.load().collection_id == "c1"

    use_case.execute(collection_id="c2")
    assert selection_repository.load().collection_id == "c2"


# --- Seleção temporária ----------------------------------------------------------------


def test_resolve_with_override_does_not_persist_selection():
    collection_repository, selection_repository, selection_service = _make_repos()
    use_case = ResolveCollectionUseCase(
        selection_service, collection_repository, selection_repository
    )

    before = selection_repository.load()
    resolved = use_case.execute(collection_id="c1")
    after = selection_repository.load()

    assert resolved.id == "c1"
    assert before == after
    assert after.collection_id is None


# --- Precedência ---------------------------------------------------------------------


def test_precedence_collection_id_wins_over_name_and_persisted():
    collection_repository, selection_repository, selection_service = _make_repos()
    selection_repository.save(ActiveSelection(workspace_id="ws-1", collection_id="c2"))
    use_case = ResolveCollectionUseCase(
        selection_service, collection_repository, selection_repository
    )

    resolved = use_case.execute(collection_id="c1", collection_name="Collection B")

    assert resolved.id == "c1"


def test_precedence_name_wins_when_id_absent():
    collection_repository, selection_repository, selection_service = _make_repos()
    selection_repository.save(ActiveSelection(workspace_id="ws-1", collection_id="c2"))
    use_case = ResolveCollectionUseCase(
        selection_service, collection_repository, selection_repository
    )

    resolved = use_case.execute(collection_name="Collection A")

    assert resolved.id == "c1"


def test_precedence_falls_back_to_persisted_selection():
    collection_repository, selection_repository, selection_service = _make_repos()
    selection_repository.save(ActiveSelection(workspace_id="ws-1", collection_id="c2"))
    use_case = ResolveCollectionUseCase(
        selection_service, collection_repository, selection_repository
    )

    resolved = use_case.execute()

    assert resolved.id == "c2"


def test_precedence_falls_back_to_interactive_when_allowed():
    collection_repository, selection_repository, selection_service = _make_repos()
    use_case = ResolveCollectionUseCase(
        selection_service, collection_repository, selection_repository
    )

    resolved = use_case.execute(
        allow_interactive=True, interactive_resolver=lambda collections: collections[1]
    )

    assert resolved.id == "c2"


def test_precedence_raises_oriented_error_when_nothing_available():
    collection_repository, selection_repository, selection_service = _make_repos()
    use_case = ResolveCollectionUseCase(
        selection_service, collection_repository, selection_repository
    )

    with pytest.raises(ResourceNotFoundError):
        use_case.execute()


def test_precedence_does_not_use_interactive_when_not_allowed():
    collection_repository, selection_repository, selection_service = _make_repos()
    use_case = ResolveCollectionUseCase(
        selection_service, collection_repository, selection_repository
    )

    with pytest.raises(ResourceNotFoundError):
        use_case.execute(
            allow_interactive=False, interactive_resolver=lambda collections: collections[0]
        )


def test_stale_persisted_collection_falls_through_to_next_precedence_level():
    collection_repository, selection_repository, selection_service = _make_repos()
    # Collection persistida não existe mais nesse Workspace: não deve travar,
    # deve seguir para o próximo nível de precedência (interativa ou erro).
    selection_repository.save(ActiveSelection(workspace_id="ws-1", collection_id="deleted-id"))
    use_case = ResolveCollectionUseCase(
        selection_service, collection_repository, selection_repository
    )

    with pytest.raises(ResourceNotFoundError):
        use_case.execute()


# --- Collection de outro Workspace -----------------------------------------------------


def test_collection_from_another_workspace_is_not_selectable():
    _, selection_repository, selection_service = _make_repos()  # ativo: ws-1
    use_case = SelectCollectionUseCase(selection_service, selection_repository)

    with pytest.raises(ResourceNotFoundError):
        use_case.execute(collection_id="c99")  # pertence a ws-2


def test_collection_from_another_workspace_is_not_resolvable():
    collection_repository, selection_repository, selection_service = _make_repos()
    use_case = ResolveCollectionUseCase(
        selection_service, collection_repository, selection_repository
    )

    with pytest.raises(ResourceNotFoundError):
        use_case.execute(collection_id="c99")


# --- Garantia de que a padrão permanece após seleção temporária -------------------------


def test_default_collection_remains_after_temporary_resolution():
    collection_repository, selection_repository, selection_service = _make_repos()
    selection_repository.save(ActiveSelection(workspace_id="ws-1", collection_id="c1"))
    use_case = ResolveCollectionUseCase(
        selection_service, collection_repository, selection_repository
    )

    use_case.execute(collection_id="c2")

    assert selection_repository.load().collection_id == "c1"


# --- Current / Clear -------------------------------------------------------------------


def test_get_current_collection_returns_persisted_id():
    _, selection_repository, _ = _make_repos()
    selection_repository.save(ActiveSelection(workspace_id="ws-1", collection_id="c1"))

    assert GetCurrentCollectionUseCase(selection_repository).execute() == "c1"


def test_get_current_collection_returns_none_when_unset():
    _, selection_repository, _ = _make_repos()

    assert GetCurrentCollectionUseCase(selection_repository).execute() is None


def test_clear_collection_preserves_active_workspace():
    _, selection_repository, _ = _make_repos()
    selection_repository.save(ActiveSelection(workspace_id="ws-1", collection_id="c1"))

    ClearCollectionUseCase(selection_repository).execute()

    assert selection_repository.load() == ActiveSelection(workspace_id="ws-1", collection_id=None)
