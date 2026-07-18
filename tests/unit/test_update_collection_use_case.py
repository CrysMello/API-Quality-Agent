import json
from pathlib import Path

import pytest

from api_quality_agent.adapters.filesystem import LocalArtifactRepository
from api_quality_agent.application.orchestration import CollectionGenerationResult
from api_quality_agent.application.use_cases import UpdateCollectionUseCase
from api_quality_agent.domain.exceptions import IntegrationError, UpdateNotApprovedError
from api_quality_agent.domain.models import (
    ActiveSelection,
    DiffCategory,
    DiffChangeType,
    DiffEntry,
    DiffResult,
    DiffRiskLevel,
    ExecutionContext,
    ExecutionMode,
    PostmanCollectionDocument,
)
from api_quality_agent.domain.services import ApprovalPolicy
from api_quality_agent.parsers import PostmanCollectionParser

_ADDED_ENTRY = DiffEntry(
    change_type=DiffChangeType.ADDED,
    category=DiffCategory.MANAGED_BLOCK,
    target="request:Ping > bloco:x",
    risk=DiffRiskLevel.LOW,
    description="Bloco gerenciado adicionado.",
)

_REMOVED_ENTRY = DiffEntry(
    change_type=DiffChangeType.REMOVED,
    category=DiffCategory.REQUEST,
    target="request:Antigo",
    risk=DiffRiskLevel.HIGH,
    description="Request removido.",
)


def _parse(name: str = "Col") -> PostmanCollectionDocument:
    document = {
        "info": {
            "name": name,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": [{"name": "Ping", "request": {"method": "GET", "url": "https://x/y"}}],
    }
    return PostmanCollectionParser().parse_text(json.dumps(document))


class _FakeCollectionRepository:
    def __init__(self, *, confirmed_id_override: str | None = None, raise_error=None) -> None:
        self.update_calls: list[tuple[str, PostmanCollectionDocument]] = []
        self._confirmed_id_override = confirmed_id_override
        self._raise_error = raise_error

    def list(self, workspace_id: str):
        return ()

    def get(self, collection_id: str):
        raise NotImplementedError

    def update(self, collection_id: str, document: PostmanCollectionDocument) -> str:
        self.update_calls.append((collection_id, document))
        if self._raise_error is not None:
            raise self._raise_error
        return self._confirmed_id_override or collection_id


class _InMemorySelectionRepository:
    def __init__(self, initial: ActiveSelection) -> None:
        self._selection = initial

    def load(self) -> ActiveSelection:
        return self._selection

    def save(self, selection: ActiveSelection) -> None:
        self._selection = selection


def _build_generation_result(
    *,
    diff_entries: tuple[DiffEntry, ...],
    collection_id: str = "c1",
    workspace_id: str = "ws-1",
    execution_id: str = "exec-1",
) -> CollectionGenerationResult:
    execution_context = ExecutionContext.create(
        mode=ExecutionMode.ONLINE,
        source="postman",
        workspace_id=workspace_id,
        collection_id=collection_id,
        collection_name="Col",
        id_factory=lambda: execution_id,
    )
    return CollectionGenerationResult(
        execution_context=execution_context,
        analysis_warnings=(),
        dependencies=(),
        endpoint_outcomes=(),
        diff=DiffResult(entries=diff_entries),
        original_document=_parse(),
        modified_document=_parse(),
        artifact_locations=(),
    )


def _build_use_case(collection_repository, tmp_path) -> UpdateCollectionUseCase:
    return UpdateCollectionUseCase(collection_repository, LocalArtifactRepository(tmp_path))


# --- Aprovado ------------------------------------------------------------------------


def test_approved_update_calls_repository_and_returns_result(tmp_path):
    repository = _FakeCollectionRepository()
    use_case = _build_use_case(repository, tmp_path)
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,))

    result = use_case.execute(generation_result, ApprovalPolicy(explicit_yes=True))

    assert result.approval.approved is True
    assert result.confirmed_collection_id == "c1"
    assert len(repository.update_calls) == 1


# --- Negado --------------------------------------------------------------------------


def test_denied_without_explicit_yes_raises_update_not_approved_error(tmp_path):
    repository = _FakeCollectionRepository()
    use_case = _build_use_case(repository, tmp_path)
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,))

    with pytest.raises(UpdateNotApprovedError):
        use_case.execute(generation_result, ApprovalPolicy(explicit_yes=False))

    assert repository.update_calls == []


# --- Dry-run ---------------------------------------------------------------------------


def test_dry_run_prevents_update_call(tmp_path):
    repository = _FakeCollectionRepository()
    use_case = _build_use_case(repository, tmp_path)
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,))

    with pytest.raises(UpdateNotApprovedError):
        use_case.execute(generation_result, ApprovalPolicy(dry_run=True, explicit_yes=True))

    assert repository.update_calls == []


# --- Remoção bloqueada -----------------------------------------------------------------


def test_unexpected_removal_blocks_update(tmp_path):
    repository = _FakeCollectionRepository()
    use_case = _build_use_case(repository, tmp_path)
    generation_result = _build_generation_result(diff_entries=(_REMOVED_ENTRY,))

    with pytest.raises(UpdateNotApprovedError):
        use_case.execute(
            generation_result, ApprovalPolicy(explicit_yes=True, allow_removals=False)
        )

    assert repository.update_calls == []


# --- ID divergente -----------------------------------------------------------------------


def test_diverging_confirmed_id_raises_integration_error(tmp_path):
    repository = _FakeCollectionRepository(confirmed_id_override="c2-outra-collection")
    use_case = _build_use_case(repository, tmp_path)
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,), collection_id="c1")

    with pytest.raises(IntegrationError):
        use_case.execute(generation_result, ApprovalPolicy(explicit_yes=True))

    assert len(repository.update_calls) == 1
    assert repository.update_calls[0][0] == "c1"


# --- Confirmação de uma única chamada ao recurso correto ---------------------------------


def test_single_call_to_correct_resource_with_unmodified_document(tmp_path):
    repository = _FakeCollectionRepository()
    use_case = _build_use_case(repository, tmp_path)
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,), collection_id="c1")

    use_case.execute(generation_result, ApprovalPolicy(explicit_yes=True))

    assert len(repository.update_calls) == 1
    called_id, called_document = repository.update_calls[0]
    assert called_id == "c1"
    # o documento enviado é exatamente o já aprovado via diff, sem reprocessamento
    # (scripts manuais preservados na geração não são rebaixados nem substituídos)
    assert called_document is generation_result.modified_document


# --- Preservação da seleção ---------------------------------------------------------------


def test_active_selection_is_preserved_after_update(tmp_path):
    selection_repository = _InMemorySelectionRepository(
        ActiveSelection(workspace_id="ws-1", collection_id="c1")
    )
    repository = _FakeCollectionRepository()
    use_case = _build_use_case(repository, tmp_path)
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,))

    use_case.execute(generation_result, ApprovalPolicy(explicit_yes=True))

    assert selection_repository.load() == ActiveSelection(workspace_id="ws-1", collection_id="c1")


# --- Backup local opcional -----------------------------------------------------------------


def test_backup_is_saved_locally_by_default(tmp_path):
    repository = _FakeCollectionRepository()
    use_case = _build_use_case(repository, tmp_path)
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,))

    result = use_case.execute(generation_result, ApprovalPolicy(explicit_yes=True))

    assert result.backup_location is not None
    backup_content = json.loads(Path(result.backup_location.path).read_text(encoding="utf-8"))
    assert backup_content["collection"]["info"]["name"] == "Col"


def test_backup_is_skipped_when_disabled(tmp_path):
    repository = _FakeCollectionRepository()
    use_case = _build_use_case(repository, tmp_path)
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,))

    result = use_case.execute(
        generation_result, ApprovalPolicy(explicit_yes=True), create_backup=False
    )

    assert result.backup_location is None


# --- Erro remoto mantém artefatos locais para diagnóstico -----------------------------------


def test_remote_error_preserves_local_backup_for_diagnosis(tmp_path):
    repository = _FakeCollectionRepository(raise_error=IntegrationError("falha simulada"))
    use_case = _build_use_case(repository, tmp_path)
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,))

    with pytest.raises(IntegrationError):
        use_case.execute(generation_result, ApprovalPolicy(explicit_yes=True))

    backup_files = list(tmp_path.rglob("original_collection.json"))
    assert len(backup_files) == 1
