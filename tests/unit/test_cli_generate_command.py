import pytest
from conftest import (
    COLLECTION_A_ID,
    COLLECTION_A_NAME,
    COLLECTION_B_ID,
    COLLECTION_B_NAME,
    DUPLICATE_COLLECTION_ID,
    FAKE_API_KEY,
    configure_server,
)

from api_quality_agent.cli.exit_codes import (
    AMBIGUOUS_SELECTION,
    INVALID_INPUT_OR_CONFIGURATION,
    OPERATION_CANCELLED,
    RESOURCE_NOT_FOUND,
    SUCCESS,
)
from api_quality_agent.cli.main import main


def _full_collection_path_was_requested(server, collection_id: str) -> bool:
    return f"/collections/{collection_id}" in server.received_paths


# --- Seleção por ID ----------------------------------------------------------------


def test_generate_by_valid_id_with_yes_flag_succeeds_without_prompting(
    cli_env, selected_workspace, monkeypatch, capsys
):
    configure_server(cli_env)
    monkeypatch.setattr(
        "builtins.input", lambda *a, **k: (_ for _ in ()).throw(AssertionError("não deveria perguntar"))
    )

    exit_code = main(["generate", "--collection-id", COLLECTION_A_ID, "--yes"])

    assert exit_code == SUCCESS
    out = capsys.readouterr().out
    assert COLLECTION_A_NAME in out
    assert "Processo concluído com sucesso" in out
    assert _full_collection_path_was_requested(cli_env, COLLECTION_A_ID)


def test_generate_by_invalid_id_reports_resource_not_found(cli_env, selected_workspace, capsys):
    configure_server(cli_env)

    exit_code = main(["generate", "--collection-id", "id-inexistente", "--yes"])

    assert exit_code == RESOURCE_NOT_FOUND
    assert FAKE_API_KEY not in capsys.readouterr().err


def test_generate_by_empty_id_reports_invalid_input(cli_env, selected_workspace, capsys):
    configure_server(cli_env)

    exit_code = main(["generate", "--collection-id", "", "--yes"])

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


# --- Seleção por nome ----------------------------------------------------------------


def test_generate_by_valid_name_succeeds(cli_env, selected_workspace, capsys):
    configure_server(cli_env)

    exit_code = main(["generate", "--collection-name", COLLECTION_B_NAME, "--yes"])

    assert exit_code == SUCCESS
    assert _full_collection_path_was_requested(cli_env, COLLECTION_B_ID)


def test_generate_by_name_not_found_reports_resource_not_found(cli_env, selected_workspace):
    configure_server(cli_env)

    exit_code = main(["generate", "--collection-name", "Nome Inexistente", "--yes"])

    assert exit_code == RESOURCE_NOT_FOUND


def test_generate_by_duplicate_name_reports_ambiguous_selection_with_both_ids(
    cli_env, selected_workspace, capsys
):
    configure_server(cli_env, duplicate_name=True)

    exit_code = main(["generate", "--collection-name", COLLECTION_A_NAME, "--yes"])

    assert exit_code == AMBIGUOUS_SELECTION
    err = capsys.readouterr().err
    assert COLLECTION_A_ID in err
    assert DUPLICATE_COLLECTION_ID in err
    assert "--collection-id" in err


# --- Seleção por índice ----------------------------------------------------------------


def test_generate_by_valid_index_succeeds(cli_env, selected_workspace, capsys):
    configure_server(cli_env)

    # Ordenação por nome: [1] Orders API (col-cli-b), [2] Pets API (col-cli-a).
    exit_code = main(["generate", "1", "--yes"])

    assert exit_code == SUCCESS
    assert _full_collection_path_was_requested(cli_env, COLLECTION_B_ID)


@pytest.mark.parametrize("index", ["0", "-1", "99"])
def test_generate_by_out_of_range_index_reports_invalid_input(
    cli_env, selected_workspace, index
):
    configure_server(cli_env)

    exit_code = main(["generate", index, "--yes"])

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


def test_generate_by_textual_index_is_rejected_by_argparse(cli_env, selected_workspace):
    configure_server(cli_env)

    with pytest.raises(SystemExit) as exc_info:
        main(["generate", "abc", "--yes"])

    assert exc_info.value.code == 2


def test_generate_index_selection_is_deterministic_across_calls(
    cli_env, selected_workspace, capsys
):
    configure_server(cli_env)

    main(["generate", "2", "--yes"])
    first_target = COLLECTION_A_ID
    assert _full_collection_path_was_requested(cli_env, first_target)


# --- Seleção interativa ----------------------------------------------------------------


def test_generate_interactive_valid_choice_succeeds(cli_env, selected_workspace, monkeypatch, capsys):
    configure_server(cli_env)
    responses = iter(["1", "s"])
    monkeypatch.setattr("builtins.input", lambda *_: next(responses))

    exit_code = main(["generate"])

    assert exit_code == SUCCESS
    out = capsys.readouterr().out
    assert "Collections disponíveis" in out
    assert _full_collection_path_was_requested(cli_env, COLLECTION_B_ID)


def test_generate_interactive_invalid_then_valid_choice_succeeds(
    cli_env, selected_workspace, monkeypatch, capsys
):
    configure_server(cli_env)
    responses = iter(["abc", "99", "2", "s"])
    monkeypatch.setattr("builtins.input", lambda *_: next(responses))

    exit_code = main(["generate"])

    assert exit_code == SUCCESS
    out = capsys.readouterr().out
    assert "Entrada inválida" in out or "Opção inválida" in out


def test_generate_interactive_empty_choice_is_rejected_then_accepts_valid(
    cli_env, selected_workspace, monkeypatch
):
    configure_server(cli_env)
    responses = iter(["", "1", "s"])
    monkeypatch.setattr("builtins.input", lambda *_: next(responses))

    exit_code = main(["generate"])

    assert exit_code == SUCCESS


def test_generate_interactive_keyboard_interrupt_cancels_operation(
    cli_env, selected_workspace, monkeypatch, capsys
):
    configure_server(cli_env)

    def _raise_keyboard_interrupt(*_a, **_k):
        raise KeyboardInterrupt()

    monkeypatch.setattr("builtins.input", _raise_keyboard_interrupt)

    exit_code = main(["generate"])

    assert exit_code == OPERATION_CANCELLED
    assert "cancelada" in capsys.readouterr().out


def test_generate_interactive_eof_cancels_operation(cli_env, selected_workspace, monkeypatch, capsys):
    configure_server(cli_env)
    monkeypatch.setattr("builtins.input", lambda *_: (_ for _ in ()).throw(EOFError()))

    exit_code = main(["generate"])

    assert exit_code == OPERATION_CANCELLED
    assert "cancelada" in capsys.readouterr().out


# --- Conflitos de seleção ----------------------------------------------------------------


def test_generate_rejects_id_and_name_together(cli_env, selected_workspace):
    configure_server(cli_env)

    exit_code = main(
        ["generate", "--collection-id", COLLECTION_A_ID, "--collection-name", COLLECTION_B_NAME]
    )

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


def test_generate_rejects_id_and_index_together(cli_env, selected_workspace):
    configure_server(cli_env)

    exit_code = main(["generate", "1", "--collection-id", COLLECTION_A_ID])

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


def test_generate_rejects_name_and_index_together(cli_env, selected_workspace):
    configure_server(cli_env)

    exit_code = main(["generate", "1", "--collection-name", COLLECTION_B_NAME])

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


def test_generate_rejects_id_name_and_index_all_together(cli_env, selected_workspace):
    configure_server(cli_env)

    exit_code = main(
        [
            "generate",
            "1",
            "--collection-id",
            COLLECTION_A_ID,
            "--collection-name",
            COLLECTION_B_NAME,
        ]
    )

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


# --- Confirmação ----------------------------------------------------------------


def test_generate_confirmation_declined_cancels_before_generating(
    cli_env, selected_workspace, monkeypatch, capsys
):
    configure_server(cli_env)
    monkeypatch.setattr("builtins.input", lambda *_: "n")

    exit_code = main(["generate", "--collection-id", COLLECTION_A_ID])

    assert exit_code == OPERATION_CANCELLED
    assert "cancelada" in capsys.readouterr().out
    assert not _full_collection_path_was_requested(cli_env, COLLECTION_A_ID)


def test_generate_confirmation_default_empty_answer_proceeds(
    cli_env, selected_workspace, monkeypatch
):
    configure_server(cli_env)
    monkeypatch.setattr("builtins.input", lambda *_: "")

    exit_code = main(["generate", "--collection-id", COLLECTION_A_ID])

    assert exit_code == SUCCESS
    assert _full_collection_path_was_requested(cli_env, COLLECTION_A_ID)


def test_generate_confirmation_unrecognized_answer_cancels(
    cli_env, selected_workspace, monkeypatch, capsys
):
    configure_server(cli_env)
    monkeypatch.setattr("builtins.input", lambda *_: "talvez")

    exit_code = main(["generate", "--collection-id", COLLECTION_A_ID])

    assert exit_code == OPERATION_CANCELLED
    out = capsys.readouterr().out
    assert "não reconhecida" in out


def test_generate_yes_flag_skips_confirmation_prompt(cli_env, selected_workspace, monkeypatch):
    configure_server(cli_env)
    monkeypatch.setattr(
        "builtins.input", lambda *a, **k: (_ for _ in ()).throw(AssertionError("não deveria perguntar"))
    )

    exit_code = main(["generate", "--collection-id", COLLECTION_A_ID, "-y"])

    assert exit_code == SUCCESS


# --- Segurança: API Key nunca vaza ----------------------------------------------------------------


def test_generate_authentication_failure_does_not_leak_api_key(
    cli_env, selected_workspace, capsys
):
    cli_env.set_route(f"/collections/{COLLECTION_A_ID}", status=401, body={"error": "invalid key"})

    exit_code = main(["generate", "--collection-id", COLLECTION_A_ID, "--yes"])

    captured = capsys.readouterr()
    assert FAKE_API_KEY not in captured.err
    assert FAKE_API_KEY not in captured.out
    assert exit_code != SUCCESS


def test_generate_server_error_does_not_leak_api_key(cli_env, selected_workspace, capsys):
    configure_server(cli_env)
    cli_env.set_route(f"/collections/{COLLECTION_A_ID}", status=500, body={"error": "boom"})

    exit_code = main(["generate", "--collection-id", COLLECTION_A_ID, "--yes"])

    captured = capsys.readouterr()
    assert FAKE_API_KEY not in captured.err
    assert FAKE_API_KEY not in captured.out
    assert exit_code != SUCCESS


def test_generate_without_active_workspace_reports_invalid_input(cli_env, capsys):
    configure_server(cli_env)

    exit_code = main(["generate", "--collection-id", COLLECTION_A_ID, "--yes"])

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION
