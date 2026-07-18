"""Cenários 17, 18 e 19 do MVP: execução Newman simulada, geração de
relatório a partir do fluxo real, e ausência da API Key em logs/artefatos
ao longo de toda a jornada.
"""

import json
import logging
from pathlib import Path

from conftest import COLLECTION_A_ID, FAKE_API_KEY, WORKSPACE_ID, build_app, configure_server

from api_quality_agent.domain.exceptions import UpdateNotApprovedError
from api_quality_agent.domain.models import BackupPolicy, SelectionOrigin
from api_quality_agent.domain.services import ApprovalPolicy


# --- Cenário 17: execução Newman simulada -------------------------------------------------


def test_scenario_17_simulated_newman_execution(postman_test_server, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "success")
    configure_server(postman_test_server)
    app = build_app(postman_test_server, tmp_path)
    app.select_workspace.execute(workspace_id=WORKSPACE_ID)
    app.select_collection.execute(collection_id=COLLECTION_A_ID)

    execution_result = app.run_use_case.execute()

    assert execution_result.success is True
    assert execution_result.infrastructure_failure is None
    assert execution_result.exit_code == 0


# --- Cenário 18: relatório ------------------------------------------------------------------


def test_scenario_18_report_reflects_the_full_flow(postman_test_server, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "test_failures")
    configure_server(postman_test_server)
    app = build_app(postman_test_server, tmp_path)
    app.select_workspace.execute(workspace_id=WORKSPACE_ID)
    app.select_collection.execute(collection_id=COLLECTION_A_ID)

    generation_result = app.generate_use_case.execute()
    postman_test_server.set_route(
        f"/collections/{COLLECTION_A_ID}",
        method="PUT",
        status=200,
        body={"collection": {"id": COLLECTION_A_ID, "uid": COLLECTION_A_ID}},
    )
    update_result = app.update_use_case.execute(
        generation_result,
        ApprovalPolicy(explicit_yes=True),
        backup_policy=BackupPolicy(enabled=True, directory=tmp_path / "backups"),
    )
    execution_result = app.run_use_case.execute()

    report = app.report_engine.generate(
        generation_result,
        selection_origin=SelectionOrigin.ACTIVE,
        update_result=update_result,
        execution_result=execution_result,
    )
    locations = app.report_engine.save(
        report,
        app.artifact_repository,
        workspace_id=WORKSPACE_ID,
        collection_id=COLLECTION_A_ID,
        execution_id=generation_result.execution_context.execution_id,
    )

    assert report.execution_id == generation_result.execution_context.execution_id
    assert report.collection_id == COLLECTION_A_ID
    assert report.update.attempted is True
    assert report.update.updated is True
    assert report.execution.executed is True
    assert len(report.execution.test_failures) >= 1

    saved_content = json.loads(Path(locations[0].path).read_text(encoding="utf-8"))
    assert saved_content["collection_id"] == COLLECTION_A_ID
    assert saved_content["execution_id"] == generation_result.execution_context.execution_id


# --- Cenário 19: API Key ausente dos logs e artefatos --------------------------------------


def test_scenario_19_api_key_never_appears_in_logs_or_artifacts(
    postman_test_server, tmp_path, monkeypatch, caplog
):
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "success")
    configure_server(postman_test_server)
    app = build_app(postman_test_server, tmp_path)

    with caplog.at_level(logging.DEBUG):
        app.select_workspace.execute(workspace_id=WORKSPACE_ID)
        app.select_collection.execute(collection_id=COLLECTION_A_ID)
        generation_result = app.generate_use_case.execute()

        try:
            app.update_use_case.execute(generation_result, ApprovalPolicy())
        except UpdateNotApprovedError:
            pass

        postman_test_server.set_route(
            f"/collections/{COLLECTION_A_ID}",
            method="PUT",
            status=200,
            body={"collection": {"id": COLLECTION_A_ID, "uid": COLLECTION_A_ID}},
        )
        update_result = app.update_use_case.execute(
            generation_result,
            ApprovalPolicy(explicit_yes=True),
            backup_policy=BackupPolicy(enabled=True, directory=tmp_path / "backups"),
        )
        execution_result = app.run_use_case.execute()
        report = app.report_engine.generate(
            generation_result, update_result=update_result, execution_result=execution_result
        )
        app.report_engine.save(
            report,
            app.artifact_repository,
            workspace_id=WORKSPACE_ID,
            collection_id=COLLECTION_A_ID,
            execution_id=generation_result.execution_context.execution_id,
        )

    # 1. Nenhum registro de log contém a API Key.
    full_log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert FAKE_API_KEY not in full_log_text

    # 2. Nenhum arquivo persistido (artefatos, backups) contém a API Key.
    for path in tmp_path.rglob("*"):
        if path.is_file():
            content = path.read_text(encoding="utf-8", errors="ignore")
            assert FAKE_API_KEY not in content, f"API Key vazou em {path}"

    # 3. A API Key nunca trafega fora do header de autenticação.
    assert all(FAKE_API_KEY not in p for p in postman_test_server.received_paths)
