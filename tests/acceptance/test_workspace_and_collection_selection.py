"""Cenários 3, 4, 5, 6, 8, 11 e 12 do MVP: conexão Postman simulada,
seleção de Workspace/Collection, alternância entre Collections, uso
temporário e resolução por nome duplicado.
"""

import pytest
from conftest import (
    COLLECTION_A_ID,
    COLLECTION_A_NAME,
    COLLECTION_B_ID,
    COLLECTION_B_NAME,
    FAKE_API_KEY,
    WORKSPACE_ID,
    WORKSPACE_NAME,
    build_app,
    configure_server,
)

from api_quality_agent.domain.exceptions import AmbiguousResourceError
from api_quality_agent.domain.models import WorkspaceRef


# --- Cenário 3: conexão Postman simulada ------------------------------------------------


def test_scenario_03_simulated_postman_connection_lists_workspaces(postman_test_server, tmp_path):
    configure_server(postman_test_server)
    app = build_app(postman_test_server, tmp_path)

    workspaces = app.list_workspaces.execute()

    assert workspaces == (WorkspaceRef(id=WORKSPACE_ID, name=WORKSPACE_NAME),)
    # "simulada": nenhuma chamada real à internet — só ao servidor HTTP local de teste.
    assert postman_test_server.base_url.startswith("http://127.0.0.1")
    assert postman_test_server.received_headers[-1]["X-Api-Key"] == FAKE_API_KEY


# --- Cenário 4: seleção de Workspace -----------------------------------------------------


def test_scenario_04_select_workspace_persists_choice(postman_test_server, tmp_path):
    configure_server(postman_test_server)
    app = build_app(postman_test_server, tmp_path)

    selected = app.select_workspace.execute(workspace_id=WORKSPACE_ID)

    assert selected.id == WORKSPACE_ID
    assert app.selection_repository.load().workspace_id == WORKSPACE_ID


# --- Cenário 5: listagem de várias Collections -------------------------------------------


def test_scenario_05_list_multiple_collections(postman_test_server, tmp_path):
    configure_server(postman_test_server)
    app = build_app(postman_test_server, tmp_path)
    app.select_workspace.execute(workspace_id=WORKSPACE_ID)

    collections = app.list_collections.execute()

    assert {c.id for c in collections} == {COLLECTION_A_ID, COLLECTION_B_ID}


# --- Cenário 6: seleção da Collection A --------------------------------------------------


def test_scenario_06_select_collection_a(postman_test_server, tmp_path):
    configure_server(postman_test_server)
    app = build_app(postman_test_server, tmp_path)
    app.select_workspace.execute(workspace_id=WORKSPACE_ID)

    selected = app.select_collection.execute(collection_id=COLLECTION_A_ID)

    assert selected.id == COLLECTION_A_ID
    assert app.selection_repository.load().collection_id == COLLECTION_A_ID


# --- Cenário 8: alternância para a Collection B ------------------------------------------


def test_scenario_08_switch_active_collection_to_b(postman_test_server, tmp_path):
    configure_server(postman_test_server)
    app = build_app(postman_test_server, tmp_path)
    app.select_workspace.execute(workspace_id=WORKSPACE_ID)
    app.select_collection.execute(collection_id=COLLECTION_A_ID)
    assert app.selection_repository.load().collection_id == COLLECTION_A_ID

    app.select_collection.execute(collection_id=COLLECTION_B_ID)

    assert app.selection_repository.load().collection_id == COLLECTION_B_ID


# --- Cenário 11: uso temporário da Collection A sem alterar B como ativa ----------------


def test_scenario_11_temporary_use_of_a_does_not_change_active_b(postman_test_server, tmp_path):
    configure_server(postman_test_server)
    app = build_app(postman_test_server, tmp_path)
    app.select_workspace.execute(workspace_id=WORKSPACE_ID)
    app.select_collection.execute(collection_id=COLLECTION_B_ID)

    # override temporário: passa o ID de A explicitamente, sem persistir seleção
    temporary_ref = app.resolve_collection.execute(collection_id=COLLECTION_A_ID)

    assert temporary_ref.id == COLLECTION_A_ID
    # a seleção ativa continua sendo B — a comprovação central da alternância segura
    assert app.selection_repository.load().collection_id == COLLECTION_B_ID


# --- Cenário 12: nome duplicado exige ID --------------------------------------------------


def test_scenario_12_duplicate_collection_name_requires_id(postman_test_server, tmp_path):
    configure_server(postman_test_server, duplicate_name=True)
    app = build_app(postman_test_server, tmp_path)
    app.select_workspace.execute(workspace_id=WORKSPACE_ID)

    with pytest.raises(AmbiguousResourceError):
        app.select_collection.execute(collection_name=COLLECTION_A_NAME)

    # com o ID explícito, a ambiguidade é resolvida
    selected = app.select_collection.execute(collection_id=COLLECTION_A_ID)
    assert selected.id == COLLECTION_A_ID
