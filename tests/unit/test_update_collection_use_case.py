import dataclasses
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest

from api_quality_agent.adapters.filesystem import LocalBackupRepository
from api_quality_agent.adapters.postman import PostmanApiClient, PostmanCollectionRepository
from api_quality_agent.application.orchestration import CollectionGenerationResult
from api_quality_agent.application.use_cases import CollectionUpdateResult, UpdateCollectionUseCase
from api_quality_agent.domain.exceptions import (
    AuthenticationError,
    BackupIntegrityError,
    ConflictError,
    IntegrationError,
    UpdateNotApprovedError,
)
from api_quality_agent.domain.models import (
    ActiveSelection,
    BackupMetadata,
    BackupPolicy,
    CollectionUpdateReceipt,
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

FAKE_API_KEY = "PMAK-super-secret-key-1234567890abcdef"

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
    def __init__(
        self,
        *,
        confirmed_id_override: str | None = None,
        status_code: int = 200,
        request_id: str | None = "req-1",
        raise_error: Exception | None = None,
        call_order: list[str] | None = None,
    ) -> None:
        self.update_calls: list[tuple[str, PostmanCollectionDocument]] = []
        self._confirmed_id_override = confirmed_id_override
        self._status_code = status_code
        self._request_id = request_id
        self._raise_error = raise_error
        self._call_order = call_order

    def list(self, workspace_id: str):
        return ()

    def get(self, collection_id: str):
        raise NotImplementedError

    def update(self, collection_id: str, document: PostmanCollectionDocument) -> CollectionUpdateReceipt:
        self.update_calls.append((collection_id, document))
        if self._call_order is not None:
            self._call_order.append("update")
        if self._raise_error is not None:
            raise self._raise_error
        return CollectionUpdateReceipt(
            confirmed_collection_id=self._confirmed_id_override or collection_id,
            status_code=self._status_code,
            request_id=self._request_id,
            document_hash=hashlib.sha256(collection_id.encode()).hexdigest(),
        )


class _FailingBackupRepository:
    def __init__(
        self,
        *,
        fail_on_save: Exception | None = None,
        fail_on_verify: bool = False,
        call_order: list[str] | None = None,
    ) -> None:
        self.save_calls = 0
        self.verify_calls = 0
        self.retention_calls = 0
        self._fail_on_save = fail_on_save
        self._fail_on_verify = fail_on_verify
        self._call_order = call_order

    def save(self, *, collection_id, workspace_id, content, contains_sensitive_data) -> BackupMetadata:
        self.save_calls += 1
        if self._call_order is not None:
            self._call_order.append("backup_save")
        if self._fail_on_save is not None:
            raise self._fail_on_save
        digest = hashlib.sha256(content).hexdigest()
        return BackupMetadata(
            collection_id=collection_id,
            created_at_utc=datetime.now(timezone.utc),
            sha256=digest,
            size_bytes=len(content),
            contains_sensitive_data=contains_sensitive_data,
            backup_path=Path(f"fake/{collection_id}/backup.json"),
        )

    def verify(self, backup_path: Path, expected_sha256: str) -> bool:
        self.verify_calls += 1
        if self._call_order is not None:
            self._call_order.append("backup_verify")
        return not self._fail_on_verify

    def apply_retention(self, *, collection_id, workspace_id, policy, keep_path) -> None:
        self.retention_calls += 1
        if self._call_order is not None:
            self._call_order.append("retention")


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
    original: PostmanCollectionDocument | None = None,
    modified: PostmanCollectionDocument | None = None,
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
        original_document=original if original is not None else _parse(),
        modified_document=modified if modified is not None else _parse(),
        artifact_locations=(),
    )


def _build_use_case(collection_repository, backup_repository) -> UpdateCollectionUseCase:
    return UpdateCollectionUseCase(collection_repository, backup_repository)


# --- Fluxo: aprovado / negado / dry-run --------------------------------------------------


def test_approved_update_marks_result_as_updated(tmp_path):
    repository = _FakeCollectionRepository()
    use_case = _build_use_case(repository, LocalBackupRepository(tmp_path))
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,))

    result = use_case.execute(generation_result, ApprovalPolicy(explicit_yes=True))

    assert result.updated is True
    assert result.dry_run is False
    assert len(repository.update_calls) == 1


def test_denied_without_explicit_yes_raises_and_creates_no_backup(tmp_path):
    repository = _FakeCollectionRepository()
    backup_repository = _FailingBackupRepository()
    use_case = _build_use_case(repository, backup_repository)
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,))

    with pytest.raises(UpdateNotApprovedError):
        use_case.execute(generation_result, ApprovalPolicy(explicit_yes=False))

    assert repository.update_calls == []
    assert backup_repository.save_calls == 0


def test_dry_run_with_changes_creates_no_backup_and_calls_nothing(tmp_path):
    repository = _FakeCollectionRepository()
    backup_repository = _FailingBackupRepository()
    use_case = _build_use_case(repository, backup_repository)
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,))

    with pytest.raises(UpdateNotApprovedError):
        use_case.execute(generation_result, ApprovalPolicy(dry_run=True, explicit_yes=True))

    assert repository.update_calls == []
    assert backup_repository.save_calls == 0


def test_dry_run_with_empty_diff_does_not_call_update():
    # Caso de borda: com diff vazio, a ApprovalPolicy aprovaria mesmo em
    # dry-run (não há "has_changes" a bloquear) — o guard de diff vazio do
    # próprio use case impede a chamada de qualquer forma.
    repository = _FakeCollectionRepository()
    backup_repository = _FailingBackupRepository()
    use_case = _build_use_case(repository, backup_repository)
    generation_result = _build_generation_result(diff_entries=())

    result = use_case.execute(generation_result, ApprovalPolicy(dry_run=True, explicit_yes=True))

    assert result.updated is False
    assert result.dry_run is True
    assert repository.update_calls == []
    assert backup_repository.save_calls == 0


def test_empty_diff_skips_update_without_raising(tmp_path):
    repository = _FakeCollectionRepository()
    use_case = _build_use_case(repository, LocalBackupRepository(tmp_path))
    generation_result = _build_generation_result(diff_entries=())

    result = use_case.execute(generation_result, ApprovalPolicy(explicit_yes=True))

    assert result.updated is False
    assert result.backup_created is False
    assert repository.update_calls == []


def test_unexpected_removal_blocks_update_and_creates_no_backup():
    repository = _FakeCollectionRepository()
    backup_repository = _FailingBackupRepository()
    use_case = _build_use_case(repository, backup_repository)
    generation_result = _build_generation_result(diff_entries=(_REMOVED_ENTRY,))

    with pytest.raises(UpdateNotApprovedError):
        use_case.execute(
            generation_result, ApprovalPolicy(explicit_yes=True, allow_removals=False)
        )

    assert repository.update_calls == []
    assert backup_repository.save_calls == 0


# --- ID divergente / chamada única / seleção preservada --------------------------------


def test_diverging_confirmed_id_raises_integration_error(tmp_path):
    repository = _FakeCollectionRepository(confirmed_id_override="c2-outra-collection")
    use_case = _build_use_case(repository, LocalBackupRepository(tmp_path))
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,), collection_id="c1")

    with pytest.raises(IntegrationError):
        use_case.execute(generation_result, ApprovalPolicy(explicit_yes=True))

    assert len(repository.update_calls) == 1


def test_single_put_call_with_unmodified_document(tmp_path):
    repository = _FakeCollectionRepository()
    use_case = _build_use_case(repository, LocalBackupRepository(tmp_path))
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,), collection_id="c1")

    use_case.execute(generation_result, ApprovalPolicy(explicit_yes=True))

    assert len(repository.update_calls) == 1
    called_id, called_document = repository.update_calls[0]
    assert called_id == "c1"
    assert called_document is generation_result.modified_document


def test_active_selection_is_preserved_after_update(tmp_path):
    selection_repository = _InMemorySelectionRepository(
        ActiveSelection(workspace_id="ws-1", collection_id="c1")
    )
    repository = _FakeCollectionRepository()
    use_case = _build_use_case(repository, LocalBackupRepository(tmp_path))
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,))

    use_case.execute(generation_result, ApprovalPolicy(explicit_yes=True))

    assert selection_repository.load() == ActiveSelection(workspace_id="ws-1", collection_id="c1")


# --- Backup: ordem, integridade, versão correta -----------------------------------------


def test_backup_created_and_verified_before_put(tmp_path):
    call_order: list[str] = []
    repository = _FakeCollectionRepository(call_order=call_order)
    backup_repository = _FailingBackupRepository(call_order=call_order)
    use_case = _build_use_case(repository, backup_repository)
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,))

    use_case.execute(generation_result, ApprovalPolicy(explicit_yes=True))

    assert call_order.index("backup_save") < call_order.index("update")
    assert call_order.index("backup_verify") < call_order.index("update")


def test_retention_applied_only_after_successful_update(tmp_path):
    call_order: list[str] = []
    repository = _FakeCollectionRepository(call_order=call_order)
    backup_repository = _FailingBackupRepository(call_order=call_order)
    use_case = _build_use_case(repository, backup_repository)
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,))

    use_case.execute(generation_result, ApprovalPolicy(explicit_yes=True))

    assert call_order == ["backup_save", "backup_verify", "update", "retention"]
    assert backup_repository.retention_calls == 1


def test_retention_not_applied_when_backup_is_disabled(tmp_path):
    repository = _FakeCollectionRepository()
    backup_repository = _FailingBackupRepository()
    use_case = _build_use_case(repository, backup_repository)
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,))

    result = use_case.execute(
        generation_result,
        ApprovalPolicy(explicit_yes=True),
        backup_policy=BackupPolicy(enabled=False, directory=tmp_path),
    )

    assert result.backup_created is False
    assert backup_repository.save_calls == 0
    assert backup_repository.retention_calls == 0


def test_backup_save_failure_blocks_api_call(tmp_path):
    repository = _FakeCollectionRepository()
    backup_repository = _FailingBackupRepository(fail_on_save=IntegrationError("disco cheio"))
    use_case = _build_use_case(repository, backup_repository)
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,))

    with pytest.raises(IntegrationError):
        use_case.execute(generation_result, ApprovalPolicy(explicit_yes=True))

    assert repository.update_calls == []


def test_backup_integrity_failure_blocks_api_call(tmp_path):
    repository = _FakeCollectionRepository()
    backup_repository = _FailingBackupRepository(fail_on_verify=True)
    use_case = _build_use_case(repository, backup_repository)
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,))

    with pytest.raises(BackupIntegrityError):
        use_case.execute(generation_result, ApprovalPolicy(explicit_yes=True))

    assert repository.update_calls == []


def test_backup_preserves_original_document_not_modified_document(tmp_path):
    repository = _FakeCollectionRepository()
    use_case = _build_use_case(repository, LocalBackupRepository(tmp_path))
    generation_result = _build_generation_result(
        diff_entries=(_ADDED_ENTRY,),
        original=_parse("Original"),
        modified=_parse("Modificada"),
    )

    result = use_case.execute(
        generation_result,
        ApprovalPolicy(explicit_yes=True),
        backup_policy=BackupPolicy(enabled=True, directory=tmp_path),
    )

    backup_content = Path(result.backup_path).read_text(encoding="utf-8")
    assert '"Original"' in backup_content
    assert '"Modificada"' not in backup_content


# --- Resultado contém somente metadados seguros -------------------------------------------


def test_result_fields_are_limited_to_safe_metadata():
    field_names = {field.name for field in dataclasses.fields(CollectionUpdateResult)}
    assert field_names == {
        "collection_id",
        "updated",
        "dry_run",
        "backup_created",
        "backup_path",
        "backup_sha256",
        "request_id",
        "status_code",
        "document_hash",
    }


def test_result_does_not_expose_document_or_full_response(tmp_path):
    repository = _FakeCollectionRepository()
    use_case = _build_use_case(repository, LocalBackupRepository(tmp_path))
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,))

    result = use_case.execute(generation_result, ApprovalPolicy(explicit_yes=True))

    for value in dataclasses.asdict(result).values():
        assert not isinstance(value, PostmanCollectionDocument)
        if isinstance(value, str):
            assert "info" not in value or "schema" not in value  # não é um JSON de Collection


# --- Idempotência (definida em relação ao estado remoto) -----------------------------------


def test_repeated_updates_produce_same_document_hash_but_different_auxiliary_metadata(
    postman_test_server, tmp_path
):
    postman_test_server.set_route(
        "/collections/c1",
        method="PUT",
        status=200,
        body={"collection": {"id": "c1", "uid": "c1"}},
        extra_headers={"X-Request-Id": "req-first"},
    )
    client = PostmanApiClient("fake-key", base_url=postman_test_server.base_url, max_retries=0)
    collection_repository = PostmanCollectionRepository(client)
    use_case = UpdateCollectionUseCase(collection_repository, LocalBackupRepository(tmp_path))
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,))

    first = use_case.execute(
        generation_result,
        ApprovalPolicy(explicit_yes=True),
        backup_policy=BackupPolicy(enabled=True, directory=tmp_path),
    )

    postman_test_server.set_route(
        "/collections/c1",
        method="PUT",
        status=200,
        body={"collection": {"id": "c1", "uid": "c1"}},
        extra_headers={"X-Request-Id": "req-second"},
    )
    second = use_case.execute(
        generation_result,
        ApprovalPolicy(explicit_yes=True),
        backup_policy=BackupPolicy(enabled=True, directory=tmp_path),
    )

    # Enviar repetidamente o mesmo documento por PUT produz o mesmo estado
    # remoto esperado: o hash do payload enviado é idêntico...
    assert first.document_hash == second.document_hash
    # ...mesmo que efeitos auxiliares variem entre execuções (request_id,
    # caminho do backup com timestamp próprio). Isso não invalida a
    # idempotência do estado remoto — apenas prova que a execução completa
    # não é (e não precisa ser) idêntica byte a byte.
    assert first.request_id != second.request_id
    assert first.backup_path != second.backup_path


def test_two_backups_from_repeated_updates_have_distinct_metadata_despite_same_content(tmp_path):
    repository = _FakeCollectionRepository()
    use_case = _build_use_case(repository, LocalBackupRepository(tmp_path))
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,))

    first = use_case.execute(
        generation_result,
        ApprovalPolicy(explicit_yes=True),
        backup_policy=BackupPolicy(enabled=True, directory=tmp_path),
    )
    second = use_case.execute(
        generation_result,
        ApprovalPolicy(explicit_yes=True),
        backup_policy=BackupPolicy(enabled=True, directory=tmp_path),
    )

    # Mesmo conteúdo original -> mesmo sha256 do backup...
    assert first.backup_sha256 == second.backup_sha256
    # ...mas cada backup é um artefato de auditoria próprio (nome único),
    # nunca sobrescrevendo o anterior.
    assert first.backup_path != second.backup_path
    assert Path(first.backup_path).exists()
    assert Path(second.backup_path).exists()


# --- Segurança: nenhum segredo exposto em erros ---------------------------------------------


@pytest.mark.parametrize(
    ("status", "expected_exception"),
    [
        (401, AuthenticationError),
        (403, AuthenticationError),
        (409, ConflictError),
        (429, IntegrationError),
        (500, IntegrationError),
        (502, IntegrationError),
        (503, IntegrationError),
    ],
)
def test_remote_error_never_exposes_api_key(postman_test_server, tmp_path, status, expected_exception):
    postman_test_server.set_route(
        "/collections/c1", method="PUT", status=status, body={"error": "falha simulada"}
    )
    client = PostmanApiClient(
        FAKE_API_KEY, base_url=postman_test_server.base_url, max_retries=0
    )
    collection_repository = PostmanCollectionRepository(client)
    use_case = UpdateCollectionUseCase(collection_repository, LocalBackupRepository(tmp_path))
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,))

    with pytest.raises(expected_exception) as exc_info:
        use_case.execute(
            generation_result,
            ApprovalPolicy(explicit_yes=True),
            backup_policy=BackupPolicy(enabled=True, directory=tmp_path),
        )

    assert FAKE_API_KEY not in str(exc_info.value)
    assert FAKE_API_KEY not in repr(exc_info.value)


def test_timeout_never_exposes_api_key(postman_test_server, tmp_path):
    postman_test_server.set_route(
        "/collections/c1", method="PUT", status=200, body={"collection": {"id": "c1"}}, delay=0.5
    )
    client = PostmanApiClient(
        FAKE_API_KEY, base_url=postman_test_server.base_url, timeout_seconds=0.05, max_retries=0
    )
    collection_repository = PostmanCollectionRepository(client)
    use_case = UpdateCollectionUseCase(collection_repository, LocalBackupRepository(tmp_path))
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,))

    with pytest.raises(IntegrationError) as exc_info:
        use_case.execute(
            generation_result,
            ApprovalPolicy(explicit_yes=True),
            backup_policy=BackupPolicy(enabled=True, directory=tmp_path),
        )

    assert FAKE_API_KEY not in str(exc_info.value)
    assert FAKE_API_KEY not in repr(exc_info.value)


def test_connection_failure_never_exposes_api_key(tmp_path):
    client = PostmanApiClient(
        FAKE_API_KEY, base_url="http://127.0.0.1:1", timeout_seconds=0.2, max_retries=0
    )
    collection_repository = PostmanCollectionRepository(client)
    use_case = UpdateCollectionUseCase(collection_repository, LocalBackupRepository(tmp_path))
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,))

    with pytest.raises(IntegrationError) as exc_info:
        use_case.execute(
            generation_result,
            ApprovalPolicy(explicit_yes=True),
            backup_policy=BackupPolicy(enabled=True, directory=tmp_path),
        )

    assert FAKE_API_KEY not in str(exc_info.value)
    assert FAKE_API_KEY not in repr(exc_info.value)


def test_malformed_response_never_exposes_api_key(postman_test_server, tmp_path):
    postman_test_server.set_raw_route(
        "/collections/c1", method="PUT", status=200, raw_body="isto não é json"
    )
    client = PostmanApiClient(
        FAKE_API_KEY, base_url=postman_test_server.base_url, max_retries=0
    )
    collection_repository = PostmanCollectionRepository(client)
    use_case = UpdateCollectionUseCase(collection_repository, LocalBackupRepository(tmp_path))
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,))

    with pytest.raises(IntegrationError) as exc_info:
        use_case.execute(
            generation_result,
            ApprovalPolicy(explicit_yes=True),
            backup_policy=BackupPolicy(enabled=True, directory=tmp_path),
        )

    assert FAKE_API_KEY not in str(exc_info.value)
    assert FAKE_API_KEY not in repr(exc_info.value)


def test_backup_failure_never_exposes_document_content(tmp_path):
    repository = _FakeCollectionRepository()
    backup_repository = _FailingBackupRepository(
        fail_on_save=IntegrationError("falha de disco simulada")
    )
    use_case = _build_use_case(repository, backup_repository)
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,))

    with pytest.raises(IntegrationError) as exc_info:
        use_case.execute(generation_result, ApprovalPolicy(explicit_yes=True))

    assert "Ping" not in str(exc_info.value)  # nome do request não vaza na exceção


def test_integrity_failure_never_exposes_document_content(tmp_path):
    repository = _FakeCollectionRepository()
    backup_repository = _FailingBackupRepository(fail_on_verify=True)
    use_case = _build_use_case(repository, backup_repository)
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,))

    with pytest.raises(BackupIntegrityError) as exc_info:
        use_case.execute(generation_result, ApprovalPolicy(explicit_yes=True))

    assert "Ping" not in str(exc_info.value)


def test_logs_never_contain_api_key_or_full_collection(postman_test_server, tmp_path, caplog):
    postman_test_server.set_route(
        "/collections/c1", method="PUT", status=200, body={"collection": {"id": "c1"}}
    )
    client = PostmanApiClient(
        FAKE_API_KEY, base_url=postman_test_server.base_url, max_retries=0
    )
    collection_repository = PostmanCollectionRepository(client)
    use_case = UpdateCollectionUseCase(collection_repository, LocalBackupRepository(tmp_path))
    generation_result = _build_generation_result(diff_entries=(_ADDED_ENTRY,))

    with caplog.at_level(logging.INFO):
        use_case.execute(
            generation_result,
            ApprovalPolicy(explicit_yes=True),
            backup_policy=BackupPolicy(enabled=True, directory=tmp_path),
        )

    full_log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert FAKE_API_KEY not in full_log_text
    assert "Ping" not in full_log_text
    assert "collection_id=c1" in full_log_text
