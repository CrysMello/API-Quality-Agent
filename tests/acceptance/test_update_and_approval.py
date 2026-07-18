"""Cenários 14, 15 e 16 do MVP: diff e aprovação, bloqueio de atualização
sem aprovação explícita, e atualização remota simulada atingindo somente a
Collection escolhida — nunca outra.
"""

import pytest
from conftest import COLLECTION_A_ID, COLLECTION_B_ID, WORKSPACE_ID, build_app, configure_server

from api_quality_agent.domain.exceptions import UpdateNotApprovedError
from api_quality_agent.domain.models import BackupPolicy
from api_quality_agent.domain.services import ApprovalPolicy


# --- Cenário 14: diff e aprovação ---------------------------------------------------------


def test_scenario_14_diff_reflects_generation_and_is_approved(postman_test_server, tmp_path):
    configure_server(postman_test_server)
    app = build_app(postman_test_server, tmp_path)
    app.select_workspace.execute(workspace_id=WORKSPACE_ID)
    app.select_collection.execute(collection_id=COLLECTION_A_ID)
    result = app.generate_use_case.execute()

    assert result.diff.has_changes is True

    approval = ApprovalPolicy(explicit_yes=True).evaluate(result.diff)

    assert approval.approved is True


# --- Cenário 15: bloqueio sem aprovação ---------------------------------------------------


def test_scenario_15_update_is_blocked_without_explicit_approval(postman_test_server, tmp_path):
    configure_server(postman_test_server)
    app = build_app(postman_test_server, tmp_path)
    app.select_workspace.execute(workspace_id=WORKSPACE_ID)
    app.select_collection.execute(collection_id=COLLECTION_A_ID)
    result = app.generate_use_case.execute()

    with pytest.raises(UpdateNotApprovedError):
        app.update_use_case.execute(result, ApprovalPolicy())  # explicit_yes=False por padrão

    put_calls = [m for m in postman_test_server.received_methods if m == "PUT"]
    assert put_calls == []


# --- Cenário 16: atualização simulada atinge somente a Collection escolhida -------------


def test_scenario_16_simulated_update_only_reaches_selected_collection(postman_test_server, tmp_path):
    configure_server(postman_test_server)
    app = build_app(postman_test_server, tmp_path)
    app.select_workspace.execute(workspace_id=WORKSPACE_ID)
    app.select_collection.execute(collection_id=COLLECTION_A_ID)
    result = app.generate_use_case.execute()

    # Somente a rota de PUT da Collection A é configurada no servidor de
    # teste: se qualquer código tentasse atualizar B por engano, a chamada
    # falharia (rota não configurada) — a asserção abaixo também confirma
    # isso de forma direta e explícita.
    postman_test_server.set_route(
        f"/collections/{COLLECTION_A_ID}",
        method="PUT",
        status=200,
        body={"collection": {"id": COLLECTION_A_ID, "uid": COLLECTION_A_ID}},
    )

    update_result = app.update_use_case.execute(
        result,
        ApprovalPolicy(explicit_yes=True),
        backup_policy=BackupPolicy(enabled=True, directory=tmp_path / "backups"),
    )

    assert update_result.updated is True
    assert update_result.collection_id == COLLECTION_A_ID

    put_paths = [
        path
        for path, method in zip(
            postman_test_server.received_paths, postman_test_server.received_methods
        )
        if method == "PUT"
    ]
    assert put_paths == [f"/collections/{COLLECTION_A_ID}"]
    assert f"/collections/{COLLECTION_B_ID}" not in put_paths
