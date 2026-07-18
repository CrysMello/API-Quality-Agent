import json
from pathlib import Path

import pytest

from api_quality_agent.application.use_cases import (
    GetCurrentWorkspaceUseCase,
    ResolveCollectionUseCase,
    RunCollectionUseCase,
)
from api_quality_agent.domain.exceptions import InputError
from api_quality_agent.domain.models import (
    ActiveSelection,
    CollectionRef,
    ExecutionResult,
)
from api_quality_agent.domain.services import CollectionSelectionService
from api_quality_agent.parsers import PostmanCollectionParser
from api_quality_agent.ports.outbound.collection_runner import DEFAULT_RUN_TIMEOUT_SECONDS


class _InMemorySelectionRepository:
    def __init__(self, initial: ActiveSelection | None = None) -> None:
        self._selection = initial or ActiveSelection()

    def load(self) -> ActiveSelection:
        return self._selection

    def save(self, selection: ActiveSelection) -> None:
        self._selection = selection


class _FakeCollectionRepository:
    def __init__(self, refs, documents_by_id) -> None:
        self._refs = refs
        self._documents_by_id = documents_by_id
        self.get_calls: list[str] = []

    def list(self, workspace_id: str):
        return self._refs

    def get(self, collection_id: str):
        self.get_calls.append(collection_id)
        return self._documents_by_id[collection_id]


class _FakeCollectionRunner:
    def __init__(self, *, raise_error: Exception | None = None) -> None:
        self.run_calls: list[dict] = []
        self.captured_content: str | None = None
        self._raise_error = raise_error

    def run(
        self,
        *,
        collection_path: str,
        environment_path: str | None = None,
        timeout_seconds: float = DEFAULT_RUN_TIMEOUT_SECONDS,
    ) -> ExecutionResult:
        self.run_calls.append(
            {
                "collection_path": collection_path,
                "environment_path": environment_path,
                "timeout_seconds": timeout_seconds,
            }
        )
        if Path(collection_path).exists():
            self.captured_content = Path(collection_path).read_text(encoding="utf-8")
        if self._raise_error is not None:
            raise self._raise_error
        return ExecutionResult(
            collection_source=collection_path,
            success=True,
            exit_code=0,
            duration_seconds=0.1,
            total_requests=1,
            total_assertions=1,
            failed_assertions=0,
            test_failures=(),
            infrastructure_failure=None,
            stdout="",
            stderr="",
        )


def _parse(name: str) -> object:
    document = {
        "info": {
            "name": name,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": [{"name": "Ping", "request": {"method": "GET", "url": "https://x/y"}}],
    }
    return PostmanCollectionParser().parse_text(json.dumps(document))


def _build_use_case(*, collection_repository, selection_repository, collection_runner):
    selection_service = CollectionSelectionService(collection_repository)
    return RunCollectionUseCase(
        GetCurrentWorkspaceUseCase(selection_repository),
        ResolveCollectionUseCase(selection_service, collection_repository, selection_repository),
        collection_repository,
        collection_runner,
    )


# --- Artefato local gerado -------------------------------------------------------------


def test_executes_local_artifact_directly(tmp_path):
    local_path = tmp_path / "generated.json"
    local_path.write_text("{}", encoding="utf-8")
    collection_repository = _FakeCollectionRepository((), {})
    selection_repository = _InMemorySelectionRepository()
    runner = _FakeCollectionRunner()
    use_case = _build_use_case(
        collection_repository=collection_repository,
        selection_repository=selection_repository,
        collection_runner=runner,
    )

    result = use_case.execute(local_collection_path=str(local_path))

    assert result.success is True
    assert len(runner.run_calls) == 1
    assert runner.run_calls[0]["collection_path"] == str(local_path)
    assert collection_repository.get_calls == []  # nunca busca a Collection remota


def test_rejects_empty_local_collection_path():
    collection_repository = _FakeCollectionRepository((), {})
    selection_repository = _InMemorySelectionRepository()
    use_case = _build_use_case(
        collection_repository=collection_repository,
        selection_repository=selection_repository,
        collection_runner=_FakeCollectionRunner(),
    )

    with pytest.raises(InputError):
        use_case.execute(local_collection_path="")


# --- Collection selecionada --------------------------------------------------------------


def test_executes_active_collection_and_materializes_temp_file():
    document = _parse("Col")
    collection_repository = _FakeCollectionRepository(
        (CollectionRef(id="c1", name="Col", workspace_id="ws-1"),), {"c1": document}
    )
    selection_repository = _InMemorySelectionRepository(
        ActiveSelection(workspace_id="ws-1", collection_id="c1")
    )
    runner = _FakeCollectionRunner()
    use_case = _build_use_case(
        collection_repository=collection_repository,
        selection_repository=selection_repository,
        collection_runner=runner,
    )

    result = use_case.execute()

    assert result.success is True
    assert collection_repository.get_calls == ["c1"]
    assert len(runner.run_calls) == 1
    assert json.loads(runner.captured_content)["collection"]["info"]["name"] == "Col"


def test_temp_file_is_removed_after_execution():
    document = _parse("Col")
    collection_repository = _FakeCollectionRepository(
        (CollectionRef(id="c1", name="Col", workspace_id="ws-1"),), {"c1": document}
    )
    selection_repository = _InMemorySelectionRepository(
        ActiveSelection(workspace_id="ws-1", collection_id="c1")
    )
    runner = _FakeCollectionRunner()
    use_case = _build_use_case(
        collection_repository=collection_repository,
        selection_repository=selection_repository,
        collection_runner=runner,
    )

    use_case.execute()

    generated_path = runner.run_calls[0]["collection_path"]
    assert not Path(generated_path).exists()


def test_temp_file_is_removed_even_when_runner_raises():
    document = _parse("Col")
    collection_repository = _FakeCollectionRepository(
        (CollectionRef(id="c1", name="Col", workspace_id="ws-1"),), {"c1": document}
    )
    selection_repository = _InMemorySelectionRepository(
        ActiveSelection(workspace_id="ws-1", collection_id="c1")
    )
    runner = _FakeCollectionRunner(raise_error=RuntimeError("falha simulada"))
    use_case = _build_use_case(
        collection_repository=collection_repository,
        selection_repository=selection_repository,
        collection_runner=runner,
    )

    with pytest.raises(RuntimeError):
        use_case.execute()

    generated_path = runner.run_calls[0]["collection_path"]
    assert not Path(generated_path).exists()


def test_temporary_collection_override_does_not_persist_selection():
    document_a = _parse("A")
    document_b = _parse("B")
    collection_repository = _FakeCollectionRepository(
        (
            CollectionRef(id="ca", name="Collection A", workspace_id="ws-1"),
            CollectionRef(id="cb", name="Collection B", workspace_id="ws-1"),
        ),
        {"ca": document_a, "cb": document_b},
    )
    selection_repository = _InMemorySelectionRepository(
        ActiveSelection(workspace_id="ws-1", collection_id="ca")
    )
    runner = _FakeCollectionRunner()
    use_case = _build_use_case(
        collection_repository=collection_repository,
        selection_repository=selection_repository,
        collection_runner=runner,
    )

    use_case.execute(collection_id="cb")

    assert collection_repository.get_calls == ["cb"]
    assert selection_repository.load().collection_id == "ca"


def test_raises_when_no_active_workspace():
    collection_repository = _FakeCollectionRepository((), {})
    selection_repository = _InMemorySelectionRepository()
    use_case = _build_use_case(
        collection_repository=collection_repository,
        selection_repository=selection_repository,
        collection_runner=_FakeCollectionRunner(),
    )

    with pytest.raises(InputError):
        use_case.execute()


# --- Environment opcional ------------------------------------------------------------------


def test_environment_is_none_by_default():
    document = _parse("Col")
    collection_repository = _FakeCollectionRepository(
        (CollectionRef(id="c1", name="Col", workspace_id="ws-1"),), {"c1": document}
    )
    selection_repository = _InMemorySelectionRepository(
        ActiveSelection(workspace_id="ws-1", collection_id="c1")
    )
    runner = _FakeCollectionRunner()
    use_case = _build_use_case(
        collection_repository=collection_repository,
        selection_repository=selection_repository,
        collection_runner=runner,
    )

    use_case.execute()

    assert runner.run_calls[0]["environment_path"] is None


def test_environment_path_is_forwarded_when_explicitly_given():
    document = _parse("Col")
    collection_repository = _FakeCollectionRepository(
        (CollectionRef(id="c1", name="Col", workspace_id="ws-1"),), {"c1": document}
    )
    selection_repository = _InMemorySelectionRepository(
        ActiveSelection(workspace_id="ws-1", collection_id="c1")
    )
    runner = _FakeCollectionRunner()
    use_case = _build_use_case(
        collection_repository=collection_repository,
        selection_repository=selection_repository,
        collection_runner=runner,
    )

    use_case.execute(environment_path="env.json")

    assert runner.run_calls[0]["environment_path"] == "env.json"


def test_rejects_empty_environment_path():
    collection_repository = _FakeCollectionRepository((), {})
    selection_repository = _InMemorySelectionRepository()
    use_case = _build_use_case(
        collection_repository=collection_repository,
        selection_repository=selection_repository,
        collection_runner=_FakeCollectionRunner(),
    )

    with pytest.raises(InputError):
        use_case.execute(local_collection_path="x.json", environment_path="")
