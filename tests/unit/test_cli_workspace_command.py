import pytest
from conftest import (
    FAKE_API_KEY,
    WORKSPACE_B_ID,
    WORKSPACE_B_NAME,
    WORKSPACE_ID,
    WORKSPACE_NAME,
    configure_server,
)

from api_quality_agent.adapters.config import FileSelectionRepository
from api_quality_agent.cli.exit_codes import (
    AMBIGUOUS_SELECTION,
    AUTHENTICATION_FAILURE,
    INVALID_INPUT_OR_CONFIGURATION,
    OPERATION_CANCELLED,
    RESOURCE_NOT_FOUND,
    SUCCESS,
)
from api_quality_agent.cli.main import main
from api_quality_agent.domain.models import ActiveSelection


# --- workspace list ----------------------------------------------------------------


def test_workspace_list_prints_numbered_workspaces_sorted_by_name(cli_env, capsys):
    configure_server(cli_env, multiple_workspaces=True)

    exit_code = main(["workspace", "list"])

    assert exit_code == SUCCESS
    out = capsys.readouterr().out
    # Ordenado por nome: "Ops Workspace" (B) vem antes de "QA Workspace".
    index_b = out.index(WORKSPACE_B_NAME)
    index_a = out.index(WORKSPACE_NAME)
    assert index_b < index_a
    assert f"[1] {WORKSPACE_B_NAME}" in out
    assert f"[2] {WORKSPACE_NAME}" in out


def test_workspace_list_with_no_workspaces_prints_friendly_message(cli_env, capsys):
    configure_server(cli_env, empty_workspaces=True)

    exit_code = main(["workspace", "list"])

    assert exit_code == SUCCESS
    assert "Nenhum Workspace foi encontrado" in capsys.readouterr().out


def test_workspace_list_never_leaks_api_key_on_authentication_failure(cli_env, capsys):
    cli_env.set_route("/workspaces", status=401, body={"error": "invalid key"})

    exit_code = main(["workspace", "list"])

    assert exit_code == AUTHENTICATION_FAILURE
    captured = capsys.readouterr()
    assert FAKE_API_KEY not in captured.out
    assert FAKE_API_KEY not in captured.err


# --- workspace select: por ID ----------------------------------------------------------------


def test_workspace_select_by_valid_id_persists_selection(
    cli_env, monkeypatch, read_active_selection, capsys
):
    configure_server(cli_env, multiple_workspaces=True)
    monkeypatch.setattr("builtins.input", lambda *_: "s")

    exit_code = main(["workspace", "select", "--workspace-id", WORKSPACE_ID])

    assert exit_code == SUCCESS
    assert read_active_selection().workspace_id == WORKSPACE_ID
    assert WORKSPACE_NAME in capsys.readouterr().out


def test_workspace_select_by_invalid_id_reports_resource_not_found(cli_env, capsys):
    configure_server(cli_env)

    exit_code = main(["workspace", "select", "--workspace-id", "id-inexistente", "--yes"])

    assert exit_code == RESOURCE_NOT_FOUND
    assert FAKE_API_KEY not in capsys.readouterr().err


def test_workspace_select_by_empty_id_reports_invalid_input(cli_env):
    configure_server(cli_env)

    exit_code = main(["workspace", "select", "--workspace-id", "", "--yes"])

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


# --- workspace select: por nome ----------------------------------------------------------------


def test_workspace_select_by_valid_name_succeeds(cli_env, read_active_selection):
    configure_server(cli_env, multiple_workspaces=True)

    exit_code = main(["workspace", "select", "--workspace-name", WORKSPACE_B_NAME, "--yes"])

    assert exit_code == SUCCESS
    assert read_active_selection().workspace_id == WORKSPACE_B_ID


def test_workspace_select_by_name_not_found_reports_resource_not_found(cli_env):
    configure_server(cli_env)

    exit_code = main(["workspace", "select", "--workspace-name", "Nome Inexistente", "--yes"])

    assert exit_code == RESOURCE_NOT_FOUND


def test_workspace_select_by_duplicate_name_reports_ambiguous_selection(cli_env, capsys):
    configure_server(cli_env, duplicate_workspace_name=True)

    exit_code = main(["workspace", "select", "--workspace-name", WORKSPACE_NAME, "--yes"])

    assert exit_code == AMBIGUOUS_SELECTION
    err = capsys.readouterr().err
    assert WORKSPACE_NAME in err
    assert "ID" in err


# --- workspace select: por índice ----------------------------------------------------------------


def test_workspace_select_by_valid_index_succeeds(cli_env, read_active_selection):
    configure_server(cli_env, multiple_workspaces=True)

    # Ordenação por nome: [1] Ops Workspace (ws-cli-2), [2] QA Workspace (ws-cli-1).
    exit_code = main(["workspace", "select", "1", "--yes"])

    assert exit_code == SUCCESS
    assert read_active_selection().workspace_id == WORKSPACE_B_ID


@pytest.mark.parametrize("index", ["0", "-1", "99"])
def test_workspace_select_by_out_of_range_index_reports_invalid_input(cli_env, index):
    configure_server(cli_env)

    exit_code = main(["workspace", "select", index, "--yes"])

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


def test_workspace_select_by_textual_index_is_rejected_by_argparse(cli_env):
    configure_server(cli_env)

    with pytest.raises(SystemExit) as exc_info:
        main(["workspace", "select", "abc", "--yes"])

    assert exc_info.value.code == 2


# --- workspace select: interativo ----------------------------------------------------------------


def test_workspace_select_interactive_valid_choice_succeeds(
    cli_env, monkeypatch, read_active_selection
):
    configure_server(cli_env, multiple_workspaces=True)
    responses = iter(["1", "s"])
    monkeypatch.setattr("builtins.input", lambda *_: next(responses))

    exit_code = main(["workspace", "select"])

    assert exit_code == SUCCESS
    assert read_active_selection().workspace_id == WORKSPACE_B_ID


def test_workspace_select_interactive_invalid_then_valid_choice_succeeds(
    cli_env, monkeypatch, read_active_selection
):
    configure_server(cli_env, multiple_workspaces=True)
    responses = iter(["abc", "99", "2", "s"])
    monkeypatch.setattr("builtins.input", lambda *_: next(responses))

    exit_code = main(["workspace", "select"])

    assert exit_code == SUCCESS
    assert read_active_selection().workspace_id == WORKSPACE_ID


def test_workspace_select_interactive_keyboard_interrupt_cancels(cli_env, monkeypatch, capsys):
    configure_server(cli_env)

    def _raise_keyboard_interrupt(*_a, **_k):
        raise KeyboardInterrupt()

    monkeypatch.setattr("builtins.input", _raise_keyboard_interrupt)

    exit_code = main(["workspace", "select"])

    assert exit_code == OPERATION_CANCELLED
    assert "cancelada" in capsys.readouterr().out


def test_workspace_select_interactive_eof_cancels(cli_env, monkeypatch, capsys):
    configure_server(cli_env)
    monkeypatch.setattr("builtins.input", lambda *_: (_ for _ in ()).throw(EOFError()))

    exit_code = main(["workspace", "select"])

    assert exit_code == OPERATION_CANCELLED
    assert "cancelada" in capsys.readouterr().out


def test_workspace_select_keyboard_interrupt_during_final_confirmation_returns_cancelled_not_unexpected_error(
    cli_env, monkeypatch, capsys
):
    # Regressão: com --workspace-id (sem seleção interativa), o Ctrl+C no
    # prompt de confirmação final antes escapava sem tratamento e virava
    # "Erro inesperado" (código 8) em vez de cancelamento (código 9).
    configure_server(cli_env)

    def _raise_keyboard_interrupt(*_a, **_k):
        raise KeyboardInterrupt()

    monkeypatch.setattr("builtins.input", _raise_keyboard_interrupt)

    exit_code = main(["workspace", "select", "--workspace-id", WORKSPACE_ID])

    assert exit_code == OPERATION_CANCELLED
    captured = capsys.readouterr()
    assert "cancelada" in captured.out
    assert "inesperado" not in captured.err.lower()


# --- workspace select: conflitos ----------------------------------------------------------------


def test_workspace_select_rejects_id_and_name_together(cli_env):
    configure_server(cli_env)

    exit_code = main(
        [
            "workspace",
            "select",
            "--workspace-id",
            WORKSPACE_ID,
            "--workspace-name",
            WORKSPACE_NAME,
        ]
    )

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


def test_workspace_select_rejects_id_and_index_together(cli_env):
    configure_server(cli_env)

    exit_code = main(["workspace", "select", "1", "--workspace-id", WORKSPACE_ID])

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


def test_workspace_select_rejects_name_and_index_together(cli_env):
    configure_server(cli_env)

    exit_code = main(["workspace", "select", "1", "--workspace-name", WORKSPACE_NAME])

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


# --- workspace select: confirmação ----------------------------------------------------------------


def test_workspace_select_confirmation_declined_does_not_persist(
    cli_env, monkeypatch, read_active_selection, capsys
):
    configure_server(cli_env)
    monkeypatch.setattr("builtins.input", lambda *_: "n")

    exit_code = main(["workspace", "select", "--workspace-id", WORKSPACE_ID])

    assert exit_code == OPERATION_CANCELLED
    assert "cancelada" in capsys.readouterr().out
    assert read_active_selection().workspace_id is None


def test_workspace_select_confirmation_default_empty_answer_proceeds(
    cli_env, monkeypatch, read_active_selection
):
    configure_server(cli_env)
    monkeypatch.setattr("builtins.input", lambda *_: "")

    exit_code = main(["workspace", "select", "--workspace-id", WORKSPACE_ID])

    assert exit_code == SUCCESS
    assert read_active_selection().workspace_id == WORKSPACE_ID


def test_workspace_select_confirmation_unrecognized_answer_cancels(
    cli_env, monkeypatch, read_active_selection, capsys
):
    configure_server(cli_env)
    monkeypatch.setattr("builtins.input", lambda *_: "talvez")

    exit_code = main(["workspace", "select", "--workspace-id", WORKSPACE_ID])

    assert exit_code == OPERATION_CANCELLED
    assert "não reconhecida" in capsys.readouterr().out
    assert read_active_selection().workspace_id is None


def test_workspace_select_yes_flag_skips_confirmation_prompt(cli_env, read_active_selection):
    configure_server(cli_env)

    exit_code = main(["workspace", "select", "--workspace-id", WORKSPACE_ID, "-y"])

    assert exit_code == SUCCESS
    assert read_active_selection().workspace_id == WORKSPACE_ID


# --- workspace select: preserva Collection ativa quando o Workspace não muda ------------------


def test_workspace_select_same_workspace_again_keeps_collection_selection(
    cli_env, tmp_path, read_active_selection
):
    configure_server(cli_env)
    FileSelectionRepository(tmp_path / "selection.json").save(
        ActiveSelection(workspace_id=WORKSPACE_ID, collection_id="col-previamente-selecionada")
    )

    exit_code = main(["workspace", "select", "--workspace-id", WORKSPACE_ID, "--yes"])

    assert exit_code == SUCCESS
    assert read_active_selection().collection_id == "col-previamente-selecionada"


def test_workspace_select_different_workspace_clears_collection_selection(
    cli_env, tmp_path, read_active_selection
):
    configure_server(cli_env, multiple_workspaces=True)
    FileSelectionRepository(tmp_path / "selection.json").save(
        ActiveSelection(workspace_id=WORKSPACE_ID, collection_id="col-previamente-selecionada")
    )

    exit_code = main(["workspace", "select", "--workspace-id", WORKSPACE_B_ID, "--yes"])

    assert exit_code == SUCCESS
    assert read_active_selection().collection_id is None
