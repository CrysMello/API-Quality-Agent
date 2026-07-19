import pytest
from conftest import (
    COLLECTION_A_ID,
    COLLECTION_A_NAME,
    COLLECTION_B_ID,
    COLLECTION_B_NAME,
    FAKE_API_KEY,
    configure_server,
)

from api_quality_agent.cli import bootstrap
from api_quality_agent.cli.exit_codes import (
    AMBIGUOUS_SELECTION,
    FUNCTIONAL_FAILURE,
    INTEGRATION_FAILURE,
    INVALID_INPUT_OR_CONFIGURATION,
    OPERATION_CANCELLED,
    RESOURCE_NOT_FOUND,
    SUCCESS,
)
from api_quality_agent.cli.main import main


# --- Seleção por ID/nome/índice/interativa (reaproveitada de generate/update) --------------------


def test_run_by_valid_id_succeeds(cli_env, selected_workspace, fake_newman, monkeypatch, capsys):
    configure_server(cli_env)
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "success")

    exit_code = main(["run", "--collection-id", COLLECTION_A_ID])

    assert exit_code == SUCCESS
    assert "Execution finished successfully." in capsys.readouterr().out


def test_run_by_invalid_id_reports_resource_not_found(cli_env, selected_workspace, fake_newman):
    configure_server(cli_env)

    exit_code = main(["run", "--collection-id", "id-inexistente"])

    assert exit_code == RESOURCE_NOT_FOUND


def test_run_by_valid_name_succeeds(cli_env, selected_workspace, fake_newman, monkeypatch):
    configure_server(cli_env)
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "success")

    exit_code = main(["run", "--collection-name", COLLECTION_B_NAME])

    assert exit_code == SUCCESS


def test_run_by_duplicate_name_reports_ambiguous_selection(cli_env, selected_workspace, fake_newman):
    configure_server(cli_env, duplicate_name=True)

    exit_code = main(["run", "--collection-name", COLLECTION_A_NAME])

    assert exit_code == AMBIGUOUS_SELECTION


def test_run_by_valid_index_succeeds(cli_env, selected_workspace, fake_newman, monkeypatch):
    configure_server(cli_env)
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "success")

    # Ordenação por nome: [1] Orders API, [2] Pets API.
    exit_code = main(["run", "1"])

    assert exit_code == SUCCESS


@pytest.mark.parametrize("index", ["0", "-1", "99"])
def test_run_by_out_of_range_index_reports_invalid_input(cli_env, selected_workspace, fake_newman, index):
    configure_server(cli_env)

    exit_code = main(["run", index])

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


def test_run_interactive_valid_choice_succeeds(cli_env, selected_workspace, fake_newman, monkeypatch):
    configure_server(cli_env)
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "success")
    monkeypatch.setattr("builtins.input", lambda *_: "1")

    exit_code = main(["run"])

    assert exit_code == SUCCESS


def test_run_interactive_invalid_then_valid_choice_succeeds(
    cli_env, selected_workspace, fake_newman, monkeypatch
):
    configure_server(cli_env)
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "success")
    responses = iter(["abc", "99", "2"])
    monkeypatch.setattr("builtins.input", lambda *_: next(responses))

    exit_code = main(["run"])

    assert exit_code == SUCCESS


def test_run_rejects_id_and_index_together(cli_env, selected_workspace, fake_newman):
    configure_server(cli_env)

    exit_code = main(["run", "1", "--collection-id", COLLECTION_A_ID])

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


def test_run_rejects_id_and_name_together(cli_env, selected_workspace, fake_newman):
    configure_server(cli_env)

    exit_code = main(
        ["run", "--collection-id", COLLECTION_A_ID, "--collection-name", COLLECTION_B_NAME]
    )

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


# --- Precedência do executável do Newman ----------------------------------------------------------------


def test_run_newman_executable_flag_is_used_when_provided(
    cli_env, selected_workspace, fake_newman, monkeypatch
):
    configure_server(cli_env)
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "success")

    main(["run", "--collection-id", COLLECTION_A_ID, "--newman-executable", "caminho-da-flag"])

    assert fake_newman.captured_executables == ["caminho-da-flag"]


def test_run_newman_executable_env_var_is_used_when_flag_absent(
    cli_env, selected_workspace, fake_newman, monkeypatch
):
    configure_server(cli_env)
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "success")
    monkeypatch.setenv("NEWMAN_EXECUTABLE", "caminho-da-env")

    main(["run", "--collection-id", COLLECTION_A_ID])

    assert fake_newman.captured_executables == ["caminho-da-env"]


def test_run_falls_back_to_default_newman_when_nothing_configured(
    cli_env, selected_workspace, fake_newman, monkeypatch
):
    configure_server(cli_env)
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "success")
    monkeypatch.delenv("NEWMAN_EXECUTABLE", raising=False)

    main(["run", "--collection-id", COLLECTION_A_ID])

    assert fake_newman.captured_executables == ["newman"]


def test_run_newman_executable_flag_takes_precedence_over_env_var(
    cli_env, selected_workspace, fake_newman, monkeypatch
):
    configure_server(cli_env)
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "success")
    monkeypatch.setenv("NEWMAN_EXECUTABLE", "caminho-da-env")

    main(
        [
            "run",
            "--collection-id",
            COLLECTION_A_ID,
            "--newman-executable",
            "caminho-da-flag",
        ]
    )

    assert fake_newman.captured_executables == ["caminho-da-flag"]


def test_run_newman_executable_accepts_windows_path_with_spaces(
    cli_env, selected_workspace, fake_newman, monkeypatch
):
    configure_server(cli_env)
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "success")
    windows_path = r"C:\Program Files\nodejs\newman.cmd"

    exit_code = main(["run", "--collection-id", COLLECTION_A_ID, "--newman-executable", windows_path])

    assert exit_code == SUCCESS
    assert fake_newman.captured_executables == [windows_path]


# --- Interpretação do ExecutionResult / mapeamento de exit code ----------------------------------------------------------------


def test_run_success_returns_zero(cli_env, selected_workspace, fake_newman, monkeypatch):
    configure_server(cli_env)
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "success")

    exit_code = main(["run", "--collection-id", COLLECTION_A_ID])

    assert exit_code == SUCCESS


def test_run_with_test_failures_returns_functional_failure(
    cli_env, selected_workspace, fake_newman, monkeypatch, capsys
):
    configure_server(cli_env)
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "with_test_failures")

    exit_code = main(["run", "--collection-id", COLLECTION_A_ID])

    assert exit_code == FUNCTIONAL_FAILURE
    out = capsys.readouterr().out
    assert "Execution finished with test failures." in out
    assert "Traceback" not in out


def test_run_with_executable_not_found_returns_integration_failure_and_guidance(
    cli_env, selected_workspace, capsys
):
    # Sem o fixture fake_newman: usa um NewmanAdapter real apontado para um
    # executável que não existe, provando a classificação real de falha de
    # infraestrutura (nenhum mock da lógica de detecção).
    configure_server(cli_env)

    exit_code = main(
        ["run", "--collection-id", COLLECTION_A_ID, "--newman-executable", "newman-que-nao-existe"]
    )

    assert exit_code == INTEGRATION_FAILURE
    out = capsys.readouterr().out
    assert "infrastructure error" in out
    assert "--newman-executable" in out
    assert "NEWMAN_EXECUTABLE" in out


def test_run_infrastructure_failure_is_not_classified_as_test_failure(
    cli_env, selected_workspace, capsys
):
    configure_server(cli_env)

    exit_code = main(
        ["run", "--collection-id", COLLECTION_A_ID, "--newman-executable", "newman-que-nao-existe"]
    )

    assert exit_code != FUNCTIONAL_FAILURE
    assert "test failures" not in capsys.readouterr().out


# --- Resumo no terminal ----------------------------------------------------------------


def test_run_summary_shows_available_fields(
    cli_env, selected_workspace, fake_newman, monkeypatch, capsys
):
    configure_server(cli_env)
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "success")

    exit_code = main(["run", "--collection-id", COLLECTION_A_ID])

    assert exit_code == SUCCESS
    out = capsys.readouterr().out
    assert "Execution Summary" in out
    assert "Workspace" in out
    assert "Collection" in out
    assert "Started" in out
    assert "Finished" in out
    assert "Duration" in out
    assert "Requests" in out
    assert "Assertions" in out
    assert "Passed" in out
    assert "Failed" in out


def test_run_summary_never_shows_artifacts_line(
    cli_env, selected_workspace, fake_newman, monkeypatch, capsys
):
    configure_server(cli_env)
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "success")

    exit_code = main(["run", "--collection-id", COLLECTION_A_ID])

    assert exit_code == SUCCESS
    assert "Artifacts" not in capsys.readouterr().out


def test_run_infrastructure_failure_does_not_print_full_summary(
    cli_env, selected_workspace, capsys
):
    configure_server(cli_env)

    main(["run", "--collection-id", COLLECTION_A_ID, "--newman-executable", "newman-que-nao-existe"])

    out = capsys.readouterr().out
    assert "Execution Summary" not in out


# --- Ctrl+C ----------------------------------------------------------------


def test_run_keyboard_interrupt_during_interactive_selection_returns_cancelled(
    cli_env, selected_workspace, fake_newman, monkeypatch, capsys
):
    configure_server(cli_env)

    def _raise_keyboard_interrupt(*_a, **_k):
        raise KeyboardInterrupt()

    monkeypatch.setattr("builtins.input", _raise_keyboard_interrupt)

    exit_code = main(["run"])

    assert exit_code == OPERATION_CANCELLED
    captured = capsys.readouterr()
    assert "cancelada" in captured.out
    assert "inesperado" not in captured.err.lower()


def test_run_keyboard_interrupt_during_execution_returns_cancelled_not_unexpected_error(
    cli_env, selected_workspace, monkeypatch, capsys
):
    configure_server(cli_env)

    class _InterruptingRunner:
        def run(self, **_kwargs):
            raise KeyboardInterrupt()

    monkeypatch.setattr(bootstrap, "NewmanAdapter", lambda **_kwargs: _InterruptingRunner())

    exit_code = main(["run", "--collection-id", COLLECTION_A_ID])

    assert exit_code == OPERATION_CANCELLED
    captured = capsys.readouterr()
    assert "cancelada" in captured.out
    assert "inesperado" not in captured.err.lower()


# --- Segurança ----------------------------------------------------------------


def test_run_never_leaks_api_key(cli_env, selected_workspace, fake_newman, monkeypatch, capsys):
    configure_server(cli_env)
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "success")

    exit_code = main(["run", "--collection-id", COLLECTION_A_ID])

    assert exit_code == SUCCESS
    captured = capsys.readouterr()
    assert FAKE_API_KEY not in captured.out
    assert FAKE_API_KEY not in captured.err


def test_run_never_prints_raw_test_failure_message_with_secret(
    cli_env, selected_workspace, fake_newman, monkeypatch, capsys
):
    # O NewmanAdapter já mascara segredos do Environment antes de devolver o
    # resultado; aqui confirmamos que o comando run também não imprime
    # stdout/stderr brutos (onde o segredo apareceria) no resumo.
    configure_server(cli_env)
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "test_failures_with_secret")
    monkeypatch.setenv("FAKE_NEWMAN_SECRET_VALUE", "segredo-super-sensivel")

    exit_code = main(["run", "--collection-id", COLLECTION_A_ID])

    assert exit_code == FUNCTIONAL_FAILURE
    captured = capsys.readouterr()
    assert "segredo-super-sensivel" not in captured.out
    assert "segredo-super-sensivel" not in captured.err
