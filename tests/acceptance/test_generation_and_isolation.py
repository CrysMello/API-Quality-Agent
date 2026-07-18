"""Cenários 7, 9, 10 e 13 do MVP: geração de testes para a Collection A,
geração para a Collection B, isolamento dos artefatos entre elas, e
preservação de script manual pré-existente durante a geração.
"""

from pathlib import Path

from conftest import COLLECTION_A_ID, COLLECTION_B_ID, WORKSPACE_ID, build_app, configure_server


def _sequential_id_factory(prefix: str):
    counter = iter(range(1, 1000))

    def _factory() -> str:
        return f"{prefix}-{next(counter)}"

    return _factory


# --- Cenário 7: geração para a Collection A ----------------------------------------------


def test_scenario_07_generate_tests_for_collection_a(postman_test_server, tmp_path):
    configure_server(postman_test_server)
    app = build_app(postman_test_server, tmp_path, id_factory=_sequential_id_factory("exec"))
    app.select_workspace.execute(workspace_id=WORKSPACE_ID)
    app.select_collection.execute(collection_id=COLLECTION_A_ID)

    result = app.generate_use_case.execute()

    assert result.execution_context.collection_id == COLLECTION_A_ID
    assert len(result.endpoint_outcomes) == 1
    assert result.endpoint_outcomes[0].error is None
    assert result.endpoint_outcomes[0].endpoint_source == "POST /pets"
    assert len(result.artifact_locations) >= 1


# --- Cenário 9: geração para a Collection B ----------------------------------------------


def test_scenario_09_generate_tests_for_collection_b(postman_test_server, tmp_path):
    configure_server(postman_test_server)
    app = build_app(postman_test_server, tmp_path, id_factory=_sequential_id_factory("exec"))
    app.select_workspace.execute(workspace_id=WORKSPACE_ID)
    app.select_collection.execute(collection_id=COLLECTION_B_ID)

    result = app.generate_use_case.execute()

    assert result.execution_context.collection_id == COLLECTION_B_ID
    assert len(result.endpoint_outcomes) == 1
    assert result.endpoint_outcomes[0].error is None
    assert result.endpoint_outcomes[0].endpoint_source == "GET /orders"


# --- Cenário 10: isolamento dos artefatos entre Collections -----------------------------


def test_scenario_10_artifacts_are_isolated_between_collections(postman_test_server, tmp_path):
    configure_server(postman_test_server)
    app = build_app(postman_test_server, tmp_path, id_factory=_sequential_id_factory("exec"))
    app.select_workspace.execute(workspace_id=WORKSPACE_ID)

    app.select_collection.execute(collection_id=COLLECTION_A_ID)
    result_a = app.generate_use_case.execute()

    app.select_collection.execute(collection_id=COLLECTION_B_ID)
    result_b = app.generate_use_case.execute()

    paths_a = {location.path for location in result_a.artifact_locations}
    paths_b = {location.path for location in result_b.artifact_locations}

    assert paths_a.isdisjoint(paths_b)
    assert all(f"{WORKSPACE_ID}\\{COLLECTION_A_ID}\\" in p or f"{WORKSPACE_ID}/{COLLECTION_A_ID}/" in p for p in paths_a)
    assert all(f"{WORKSPACE_ID}\\{COLLECTION_B_ID}\\" in p or f"{WORKSPACE_ID}/{COLLECTION_B_ID}/" in p for p in paths_b)

    # conteúdo de A nunca menciona o endpoint de B, e vice-versa
    content_a = "\n".join(Path(p).read_text(encoding="utf-8") for p in paths_a)
    content_b = "\n".join(Path(p).read_text(encoding="utf-8") for p in paths_b)
    assert "orders" not in content_a.lower()
    assert "pets" not in content_b.lower()


# --- Cenário 13: preservação de script manual ---------------------------------------------


def test_scenario_13_manual_script_is_preserved_during_generation(postman_test_server, tmp_path):
    configure_server(postman_test_server, with_manual_script_in_a=True)
    app = build_app(postman_test_server, tmp_path, id_factory=_sequential_id_factory("exec"))
    app.select_workspace.execute(workspace_id=WORKSPACE_ID)
    app.select_collection.execute(collection_id=COLLECTION_A_ID)

    result = app.generate_use_case.execute()

    outcome = result.endpoint_outcomes[0]
    assert "// script manual do time" in outcome.merged_script
    assert "console.log('preservar isto');" in outcome.merged_script
    # o bloco gerenciado gerado também está presente, ao lado do manual
    assert "pm.response.to.have.status(201)" in outcome.merged_script
    # o código manual nunca é reportado como removido no diff
    assert not any("preservar isto" in entry.description for entry in result.diff.entries)
