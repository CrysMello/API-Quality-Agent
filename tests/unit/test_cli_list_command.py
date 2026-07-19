from conftest import (
    COLLECTION_A_ID,
    COLLECTION_A_NAME,
    COLLECTION_B_ID,
    COLLECTION_B_NAME,
    FAKE_API_KEY,
    WORKSPACE_NAME,
    configure_server,
)

from api_quality_agent.cli.exit_codes import (
    AUTHENTICATION_FAILURE,
    INVALID_INPUT_OR_CONFIGURATION,
    RESOURCE_NOT_FOUND,
)
from api_quality_agent.cli.main import main


def test_list_without_active_workspace_reports_invalid_input(cli_env, capsys):
    configure_server(cli_env)

    exit_code = main(["list"])

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION
    captured = capsys.readouterr()
    assert "Workspace" in captured.err


def test_list_without_api_key_reports_configuration_error(monkeypatch, capsys):
    monkeypatch.delenv("POSTMAN_API_KEY", raising=False)

    exit_code = main(["list"])

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION
    captured = capsys.readouterr()
    assert FAKE_API_KEY not in captured.err


def test_list_prints_numbered_collections_sorted_by_name(cli_env, selected_workspace, capsys):
    configure_server(cli_env)

    exit_code = main(["list"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert WORKSPACE_NAME in out
    # Ordenado por nome: "Orders API" (B) vem antes de "Pets API" (A).
    index_b = out.index(COLLECTION_B_NAME)
    index_a = out.index(COLLECTION_A_NAME)
    assert index_b < index_a
    assert f"[1] {COLLECTION_B_NAME}" in out
    assert COLLECTION_B_ID in out
    assert f"[2] {COLLECTION_A_NAME}" in out
    assert COLLECTION_A_ID in out


def test_list_with_no_collections_prints_friendly_message(cli_env, selected_workspace, capsys):
    configure_server(cli_env, empty_collections=True)

    exit_code = main(["list"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Nenhuma Collection foi encontrada" in out


def test_list_with_duplicate_collection_names_lists_both_with_ids(
    cli_env, selected_workspace, capsys
):
    configure_server(cli_env, duplicate_name=True)

    exit_code = main(["list"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert out.count(COLLECTION_A_NAME) == 2


def test_list_reports_authentication_failure_without_leaking_key(
    cli_env, selected_workspace, capsys
):
    cli_env.set_route("/workspaces", status=401, body={"error": "invalid key"})

    exit_code = main(["list"])

    assert exit_code == AUTHENTICATION_FAILURE
    captured = capsys.readouterr()
    assert FAKE_API_KEY not in captured.err
    assert FAKE_API_KEY not in captured.out


def test_list_reports_resource_not_found_when_active_workspace_vanished(
    cli_env, selected_workspace, capsys
):
    configure_server(cli_env, workspaces=[])

    exit_code = main(["list"])

    assert exit_code == RESOURCE_NOT_FOUND
