"""A API Key nunca deve aparecer em stdout/stderr da CLI, seja qual for o
tipo de falha retornada pelo Postman. PostmanApiClient já é exaustivamente
testado (401/403/409/429/5xx/timeout) em test_postman_api_client.py; aqui
verificamos a ponta a ponta: que a camada CLI (main._dispatch + comandos)
também nunca imprime a chave ao formatar qualquer exceção.
"""

import pytest
from conftest import FAKE_API_KEY, configure_server

from api_quality_agent.cli.exit_codes import (
    AUTHENTICATION_FAILURE,
    INTEGRATION_FAILURE,
    SUCCESS,
)
from api_quality_agent.cli.main import main


@pytest.mark.parametrize(
    "status,expected_exit_code",
    [
        (401, AUTHENTICATION_FAILURE),
        (403, AUTHENTICATION_FAILURE),
        (409, INTEGRATION_FAILURE),
        (500, INTEGRATION_FAILURE),
        (503, INTEGRATION_FAILURE),
    ],
)
def test_list_command_never_leaks_api_key_on_http_failure(
    cli_env, selected_workspace, capsys, status, expected_exit_code
):
    cli_env.set_route("/workspaces", status=status, body={"error": "falha simulada"})

    exit_code = main(["list"])

    captured = capsys.readouterr()
    assert FAKE_API_KEY not in captured.out
    assert FAKE_API_KEY not in captured.err
    assert exit_code == expected_exit_code
    assert exit_code != SUCCESS


def test_list_command_never_leaks_api_key_after_rate_limit_exhausts_retries(
    cli_env, selected_workspace, capsys
):
    cli_env.set_route("/workspaces", status=429, body={"error": "rate limited"})

    exit_code = main(["list"])

    captured = capsys.readouterr()
    assert FAKE_API_KEY not in captured.out
    assert FAKE_API_KEY not in captured.err
    assert exit_code == INTEGRATION_FAILURE


def test_list_command_never_leaks_api_key_on_timeout(cli_env, selected_workspace, capsys):
    # O fixture cli_env configura o cliente com timeout_seconds=2.0 e
    # max_retries=0; um atraso maior que isso força um timeout real de rede
    # em uma única tentativa, sem precisar mockar a camada HTTP.
    cli_env.set_route("/workspaces", status=200, body={"workspaces": []}, delay=2.5)

    exit_code = main(["list"])

    captured = capsys.readouterr()
    assert FAKE_API_KEY not in captured.out
    assert FAKE_API_KEY not in captured.err
    assert exit_code != SUCCESS
