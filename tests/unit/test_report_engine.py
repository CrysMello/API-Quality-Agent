import json
from datetime import datetime, timezone
from pathlib import Path

from api_quality_agent import __version__
from api_quality_agent.adapters.filesystem import LocalArtifactRepository
from api_quality_agent.application.orchestration import (
    AgentOrchestrator,
    CollectionGenerationResult,
)
from api_quality_agent.application.use_cases import CollectionUpdateResult
from api_quality_agent.domain.models import (
    ExecutionContext,
    ExecutionMode,
    ExecutionResult,
    InfrastructureFailure,
    InfrastructureFailureType,
    SelectionOrigin,
    TestFailure,
)
from api_quality_agent.domain.services import (
    ApiAnalysisEngine,
    DiffEngine,
    ManagedBlockMerger,
    SchemaInferenceEngine,
    TestStrategyEngine,
)
from api_quality_agent.generators import PostmanTestGenerator
from api_quality_agent.parsers import PostmanCollectionParser
from api_quality_agent.reporting import ReportEngine, render_report_html, render_report_json
from api_quality_agent.reporting.report_serializer import (
    REPORT_SCHEMA_TOP_LEVEL_KEYS,
    serialize_report,
)
from api_quality_agent.reporting.report_summary_renderer import render_report_summary

STARTED_AT = datetime(2026, 7, 18, 10, 0, 0, tzinfo=timezone.utc)
GENERATED_AT = datetime(2026, 7, 18, 10, 0, 5, tzinfo=timezone.utc)


def _parse(items: list, *, name: str = "Col") -> object:
    document = {
        "info": {
            "name": name,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": items,
    }
    return PostmanCollectionParser().parse_text(json.dumps(document))


def _build_generation_result(
    items: list,
    *,
    execution_id: str = "exec-1",
    collection_id: str = "c1",
    workspace_id: str = "ws-1",
    name: str = "Col",
) -> CollectionGenerationResult:
    document = _parse(items, name=name)
    orchestrator = AgentOrchestrator(
        ApiAnalysisEngine(),
        SchemaInferenceEngine(),
        TestStrategyEngine(),
        PostmanTestGenerator(),
        ManagedBlockMerger(),
        DiffEngine(),
    )
    execution_context = ExecutionContext.create(
        mode=ExecutionMode.ONLINE,
        source="postman",
        workspace_id=workspace_id,
        collection_id=collection_id,
        collection_name=name,
        id_factory=lambda: execution_id,
        clock=lambda: STARTED_AT,
    )
    return orchestrator.process(document, execution_context)


def _build_engine() -> ReportEngine:
    return ReportEngine(clock=lambda: GENERATED_AT)


_SUCCESSFUL_REQUEST = {
    "name": "Criar pet",
    "id": "r1",
    "request": {"method": "POST", "url": "https://x/pets"},
    "response": [{"name": "ok", "status": "OK", "code": 201, "header": [], "body": "{}"}],
}


# --- Somente geração ---------------------------------------------------------------------


def test_report_with_generation_only():
    generation_result = _build_generation_result([_SUCCESSFUL_REQUEST])
    report = _build_engine().generate(generation_result)

    assert report.execution_id == "exec-1"
    assert report.mode == "online"
    assert report.source == "postman"
    assert report.workspace_id == "ws-1"
    assert report.collection_id == "c1"
    assert report.selection_origin == SelectionOrigin.ACTIVE.value
    assert report.generated_at == GENERATED_AT
    assert report.duration_seconds == 5.0
    assert len(report.endpoints) == 1
    assert report.endpoints[0].succeeded is True
    assert report.endpoints[0].test_count >= 1
    assert report.update.attempted is False
    assert report.execution.executed is False
    assert report.agent_version == __version__


# --- Geração e atualização -----------------------------------------------------------------


def test_report_with_approved_update():
    generation_result = _build_generation_result([_SUCCESSFUL_REQUEST])
    update_result = CollectionUpdateResult(
        collection_id="c1",
        updated=True,
        dry_run=False,
        backup_created=True,
        backup_path=Path("backups/ws-1/c1/backup.json"),
        backup_sha256="a" * 64,
        request_id="req-1",
        status_code=200,
        document_hash="b" * 64,
    )

    report = _build_engine().generate(generation_result, update_result=update_result)

    assert report.update.attempted is True
    assert report.update.approved is True
    assert report.update.updated is True
    assert report.update.backup_created is True
    assert report.update.status_code == 200
    assert report.update.denial_reason is None


def test_report_with_denied_update():
    generation_result = _build_generation_result([_SUCCESSFUL_REQUEST])

    report = _build_engine().generate(
        generation_result, update_denied_reason="Nenhuma aprovação explícita foi fornecida."
    )

    assert report.update.attempted is True
    assert report.update.approved is False
    assert report.update.updated is False
    assert "aprovação" in report.update.denial_reason


# --- Geração e Newman ------------------------------------------------------------------------


def test_report_with_newman_execution():
    generation_result = _build_generation_result([_SUCCESSFUL_REQUEST])
    execution_result = ExecutionResult(
        collection_source="collection.json",
        success=False,
        exit_code=1,
        duration_seconds=1.23,
        total_requests=1,
        total_assertions=2,
        failed_assertions=1,
        test_failures=(
            TestFailure(
                request_name="Criar pet", test_name="Status 201", error_message="expected 500"
            ),
        ),
        infrastructure_failure=None,
        stdout="{}",
        stderr="",
    )

    report = _build_engine().generate(generation_result, execution_result=execution_result)

    assert report.execution.executed is True
    assert report.execution.success is False
    assert report.execution.exit_code == 1
    assert report.execution.failed_assertions == 1
    assert len(report.execution.test_failures) == 1
    assert report.execution.infrastructure_failure is None


def test_report_can_be_generated_without_newman_execution():
    generation_result = _build_generation_result([_SUCCESSFUL_REQUEST])

    report = _build_engine().generate(generation_result)

    assert report.execution.executed is False
    assert report.execution.test_failures == ()
    assert report.execution.infrastructure_failure is None


# --- Erro de infraestrutura ------------------------------------------------------------------


def test_report_with_infrastructure_failure():
    generation_result = _build_generation_result([_SUCCESSFUL_REQUEST])
    execution_result = ExecutionResult(
        collection_source="collection.json",
        success=False,
        exit_code=None,
        duration_seconds=0.3,
        total_requests=0,
        total_assertions=0,
        failed_assertions=0,
        test_failures=(),
        infrastructure_failure=InfrastructureFailure(
            failure_type=InfrastructureFailureType.TIMEOUT,
            message="Execução do Newman excedeu o tempo limite de 5s.",
        ),
        stdout="",
        stderr="",
    )

    report = _build_engine().generate(generation_result, execution_result=execution_result)

    assert report.execution.infrastructure_failure is not None
    assert report.execution.infrastructure_failure.failure_type == "timeout"
    # falha de infraestrutura não deve ser confundida com falha de teste
    assert report.execution.test_failures == ()

    # continua serializável mesmo com falha de infraestrutura
    serialized = serialize_report(report)
    json.dumps(serialized)


# --- Mascaramento --------------------------------------------------------------------------


def test_report_never_exposes_raw_authorization_header_value():
    secret_value = "Bearer sk_live_super_secret_abcdef123456"
    request_with_secret = {
        "name": "Ping",
        "id": "r1",
        "request": {
            "method": "GET",
            "url": "https://x/y",
            "header": [{"key": "Authorization", "value": secret_value}],
            "auth": {"type": "bearer", "bearer": [{"key": "token", "value": secret_value}]},
        },
    }
    generation_result = _build_generation_result([request_with_secret])

    report = _build_engine().generate(generation_result)

    json_text = render_report_json(report)
    html_text = render_report_html(report)
    summary_text = render_report_summary(report)

    assert secret_value not in json_text
    assert secret_value not in html_text
    assert secret_value not in summary_text


def test_report_passes_through_already_masked_newman_failure_message():
    generation_result = _build_generation_result([_SUCCESSFUL_REQUEST])
    masked_message = "expected response to contain token sk_l****3456"
    execution_result = ExecutionResult(
        collection_source="collection.json",
        success=False,
        exit_code=1,
        duration_seconds=0.1,
        total_requests=1,
        total_assertions=1,
        failed_assertions=1,
        test_failures=(
            TestFailure(request_name="Ping", test_name="token", error_message=masked_message),
        ),
        infrastructure_failure=None,
        stdout="",
        stderr="",
    )

    report = _build_engine().generate(generation_result, execution_result=execution_result)

    assert report.execution.test_failures[0].error_message == masked_message
    assert masked_message in render_report_json(report)


# --- HTML escaping -------------------------------------------------------------------------


def test_html_escapes_malicious_content_in_collection_name():
    generation_result = _build_generation_result(
        [_SUCCESSFUL_REQUEST], name='<script>alert("xss")</script>'
    )

    html_text = render_report_html(_build_engine().generate(generation_result))

    assert "<script>alert" not in html_text
    assert "&lt;script&gt;" in html_text


def test_html_escapes_malicious_content_in_denial_reason():
    generation_result = _build_generation_result([_SUCCESSFUL_REQUEST])

    html_text = render_report_html(
        _build_engine().generate(
            generation_result, update_denied_reason='<img src=x onerror="alert(1)">'
        )
    )

    assert "<img src=x" not in html_text
    assert "&lt;img" in html_text


# --- JSON serializável -----------------------------------------------------------------------


def test_json_report_round_trips_and_has_stable_schema():
    generation_result = _build_generation_result([_SUCCESSFUL_REQUEST])
    report = _build_engine().generate(generation_result)

    serialized = serialize_report(report)
    assert set(serialized.keys()) == set(REPORT_SCHEMA_TOP_LEVEL_KEYS)

    round_tripped = json.loads(render_report_json(report))
    assert round_tripped == serialized


def test_json_report_is_serializable_with_update_and_execution():
    generation_result = _build_generation_result([_SUCCESSFUL_REQUEST])
    update_result = CollectionUpdateResult(
        collection_id="c1",
        updated=True,
        dry_run=False,
        backup_created=False,
        backup_path=None,
        backup_sha256=None,
        request_id=None,
        status_code=200,
        document_hash="c" * 64,
    )
    execution_result = ExecutionResult(
        collection_source="c.json",
        success=True,
        exit_code=0,
        duration_seconds=0.5,
        total_requests=1,
        total_assertions=1,
        failed_assertions=0,
        test_failures=(),
        infrastructure_failure=None,
        stdout="",
        stderr="",
    )

    report = _build_engine().generate(
        generation_result, update_result=update_result, execution_result=execution_result
    )

    # não deve levantar
    json.dumps(serialize_report(report))


# --- Isolamento de diretórios ---------------------------------------------------------------


def test_reports_for_different_collections_are_isolated_on_disk(tmp_path):
    artifact_repository = LocalArtifactRepository(tmp_path)
    engine = _build_engine()

    result_a = _build_generation_result(
        [_SUCCESSFUL_REQUEST], execution_id="exec-a", collection_id="ca", workspace_id="ws-1"
    )
    result_b = _build_generation_result(
        [_SUCCESSFUL_REQUEST], execution_id="exec-b", collection_id="cb", workspace_id="ws-1"
    )

    locations_a = engine.save(
        engine.generate(result_a),
        artifact_repository,
        workspace_id="ws-1",
        collection_id="ca",
        execution_id="exec-a",
    )
    locations_b = engine.save(
        engine.generate(result_b),
        artifact_repository,
        workspace_id="ws-1",
        collection_id="cb",
        execution_id="exec-b",
    )

    assert locations_a[0].path != locations_b[0].path
    assert str(tmp_path / "ws-1" / "ca" / "exec-a") in locations_a[0].path
    assert str(tmp_path / "ws-1" / "cb" / "exec-b") in locations_b[0].path

    content_a = json.loads(Path(locations_a[0].path).read_text(encoding="utf-8"))
    content_b = json.loads(Path(locations_b[0].path).read_text(encoding="utf-8"))
    assert content_a["collection_id"] == "ca"
    assert content_b["collection_id"] == "cb"


def test_report_paths_use_execution_id_and_never_collide_across_executions(tmp_path):
    artifact_repository = LocalArtifactRepository(tmp_path)
    engine = _build_engine()

    result_1 = _build_generation_result(
        [_SUCCESSFUL_REQUEST], execution_id="exec-1", collection_id="c1", workspace_id="ws-1"
    )
    result_2 = _build_generation_result(
        [_SUCCESSFUL_REQUEST], execution_id="exec-2", collection_id="c1", workspace_id="ws-1"
    )

    locations_1 = engine.save(
        engine.generate(result_1),
        artifact_repository,
        workspace_id="ws-1",
        collection_id="c1",
        execution_id="exec-1",
    )
    locations_2 = engine.save(
        engine.generate(result_2),
        artifact_repository,
        workspace_id="ws-1",
        collection_id="c1",
        execution_id="exec-2",
    )

    assert locations_1[0].path != locations_2[0].path
    assert Path(locations_1[0].path).exists()
    assert Path(locations_2[0].path).exists()


def test_save_includes_html_only_when_requested(tmp_path):
    artifact_repository = LocalArtifactRepository(tmp_path)
    engine = _build_engine()
    generation_result = _build_generation_result([_SUCCESSFUL_REQUEST])
    report = engine.generate(generation_result)

    json_only = engine.save(
        report,
        artifact_repository,
        workspace_id="ws-1",
        collection_id="c1",
        execution_id="exec-json-only",
    )
    with_html = engine.save(
        report,
        artifact_repository,
        workspace_id="ws-1",
        collection_id="c1",
        execution_id="exec-with-html",
        include_html=True,
    )

    assert len(json_only) == 1
    assert len(with_html) == 2
    assert any(path.path.endswith("report.html") for path in with_html)
