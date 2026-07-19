"""Testes de fumaça em nível de subprocesso real (python -m ...), garantindo
que o entry point funciona fora do processo de teste. Cobrem apenas os
caminhos que não dependem de rede real com o Postman (--help, version, e
comandos sem POSTMAN_API_KEY configurada) — os fluxos completos de list/
generate contra um servidor controlado já são cobertos em processo (mais
rápido e sem custo de I/O de subprocesso) pelos demais arquivos de teste
desta pasta.
"""

import json
import subprocess
import sys

from api_quality_agent import __version__

_CLI_MODULE = "api_quality_agent.cli.main"


def _run_cli(
    *args: str, env: dict[str, str] | None = None, cwd: str | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", _CLI_MODULE, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=cwd,
        timeout=30,
    )


def test_root_help_exits_zero_and_lists_subcommands():
    result = _run_cli("--help")

    assert result.returncode == 0
    assert "workspace" in result.stdout
    assert "list" in result.stdout
    assert "generate" in result.stdout
    assert "version" in result.stdout


def test_root_version_flag_exits_zero():
    result = _run_cli("--version")

    assert result.returncode == 0
    assert __version__ in result.stdout


def test_version_subcommand_exits_zero():
    result = _run_cli("version")

    assert result.returncode == 0
    assert __version__ in result.stdout
    assert "API Quality Agent" in result.stdout


def test_generate_help_exits_zero_and_documents_flags():
    result = _run_cli("generate", "--help")

    assert result.returncode == 0
    assert "--collection-id" in result.stdout
    assert "--collection-name" in result.stdout
    assert "--file" in result.stdout
    assert "--yes" in result.stdout


def test_list_help_exits_zero():
    result = _run_cli("list", "--help")

    assert result.returncode == 0


def test_workspace_help_exits_zero_and_lists_subcommands():
    result = _run_cli("workspace", "--help")

    assert result.returncode == 0
    assert "list" in result.stdout
    assert "select" in result.stdout


def test_workspace_select_help_exits_zero_and_documents_flags():
    result = _run_cli("workspace", "select", "--help")

    assert result.returncode == 0
    assert "--workspace-id" in result.stdout
    assert "--workspace-name" in result.stdout
    assert "--yes" in result.stdout


def test_list_without_api_key_fails_fast_without_network(no_api_key_env):
    result = _run_cli("list", env=no_api_key_env)

    assert result.returncode == 2
    assert "POSTMAN_API_KEY" in result.stderr
    assert "não" in result.stderr


def test_generate_without_api_key_fails_fast_without_network(no_api_key_env):
    result = _run_cli("generate", "--collection-id", "qualquer", env=no_api_key_env)

    assert result.returncode == 2
    assert "POSTMAN_API_KEY" in result.stderr


def test_workspace_list_without_api_key_fails_fast_without_network(no_api_key_env):
    result = _run_cli("workspace", "list", env=no_api_key_env)

    assert result.returncode == 2
    assert "POSTMAN_API_KEY" in result.stderr


def test_workspace_select_without_api_key_fails_fast_without_network(no_api_key_env):
    result = _run_cli("workspace", "select", "--workspace-id", "qualquer", env=no_api_key_env)

    assert result.returncode == 2
    assert "POSTMAN_API_KEY" in result.stderr


def test_generate_from_file_works_in_a_real_subprocess_without_api_key(no_api_key_env, tmp_path):
    document = {
        "info": {
            "name": "Subprocess Collection",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": [
            {
                "name": "Ping",
                "id": "req-1",
                "request": {"method": "GET", "url": "https://api.exemplo.com/ping"},
                "response": [{"name": "ok", "status": "OK", "code": 200, "header": [], "body": "{}"}],
            }
        ],
    }
    collection_path = tmp_path / "collection.json"
    collection_path.write_text(json.dumps(document), encoding="utf-8")

    result = _run_cli(
        "generate", "--file", "collection.json", "--yes", env=no_api_key_env, cwd=str(tmp_path)
    )

    assert result.returncode == 0
    assert "Subprocess Collection" in result.stdout
    assert (tmp_path / "artifacts" / "local").is_dir()


def test_unknown_command_exits_with_argparse_usage_error():
    result = _run_cli("comando-inexistente")

    assert result.returncode == 2
