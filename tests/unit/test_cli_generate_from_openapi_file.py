import json

import pytest
from conftest import COLLECTION_A_ID, FAKE_API_KEY, configure_server

from api_quality_agent.cli.exit_codes import (
    INVALID_INPUT_OR_CONFIGURATION,
    OPERATION_CANCELLED,
    SUCCESS,
)
from api_quality_agent.cli.main import main


def _write_openapi_file(path, *, title="Pets API"):
    document = {
        "openapi": "3.0.0",
        "info": {"title": title, "version": "1.0"},
        "servers": [{"url": "https://api.exemplo.com/v1"}],
        "paths": {
            "/pets/{petId}": {
                "get": {
                    "operationId": "getPet",
                    "summary": "Busca um pet",
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object"},
                                    "example": {"id": 1, "name": "Rex"},
                                }
                            },
                        }
                    },
                }
            }
        },
    }
    file_path = path / "openapi.json"
    file_path.write_text(json.dumps(document), encoding="utf-8")
    return file_path


# --- Fluxo feliz, sem API Key ----------------------------------------------------------------


def test_generate_from_openapi_file_succeeds_without_api_key(offline_env, capsys):
    file_path = _write_openapi_file(offline_env)

    exit_code = main(["generate", "--openapi-file", str(file_path), "--yes"])

    assert exit_code == SUCCESS
    out = capsys.readouterr().out
    assert "Pets API" in out
    assert "Endpoints processados: 1" in out


def test_generate_from_openapi_file_never_requires_postman_api_key_env_var(
    offline_env, monkeypatch, capsys
):
    monkeypatch.delenv("POSTMAN_API_KEY", raising=False)
    file_path = _write_openapi_file(offline_env)

    exit_code = main(["generate", "--openapi-file", str(file_path), "--yes"])

    assert exit_code == SUCCESS


def test_generate_from_openapi_file_saves_a_collection_json_artifact(offline_env, capsys):
    file_path = _write_openapi_file(offline_env)

    exit_code = main(["generate", "--openapi-file", str(file_path), "--yes"])

    assert exit_code == SUCCESS
    out = capsys.readouterr().out
    assert "collection.json" in out
    artifacts_dir = offline_env / "artifacts" / "local"
    assert artifacts_dir.is_dir()


# --- Arquivo inválido ----------------------------------------------------------------


def test_generate_from_openapi_file_with_missing_file_reports_invalid_input(offline_env, capsys):
    missing_path = offline_env / "nao_existe.json"

    exit_code = main(["generate", "--openapi-file", str(missing_path), "--yes"])

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION
    assert "encontrado" in capsys.readouterr().err.lower()


def test_generate_from_openapi_file_with_invalid_spec_reports_invalid_input(offline_env, capsys):
    file_path = offline_env / "nao_e_spec.json"
    file_path.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")

    exit_code = main(["generate", "--openapi-file", str(file_path), "--yes"])

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


# --- Conflitos com outras formas de seleção ----------------------------------------------------------------


def test_generate_rejects_openapi_file_and_collection_id_together(offline_env):
    file_path = _write_openapi_file(offline_env)

    exit_code = main(
        ["generate", "--openapi-file", str(file_path), "--collection-id", COLLECTION_A_ID, "--yes"]
    )

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


def test_generate_rejects_file_and_openapi_file_together(offline_env):
    file_path = _write_openapi_file(offline_env)

    exit_code = main(
        ["generate", "--file", str(file_path), "--openapi-file", str(file_path), "--yes"]
    )

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


# --- Confirmação ----------------------------------------------------------------


def test_generate_from_openapi_file_confirmation_declined_cancels(offline_env, monkeypatch, capsys):
    file_path = _write_openapi_file(offline_env)
    monkeypatch.setattr("builtins.input", lambda *_: "n")

    exit_code = main(["generate", "--openapi-file", str(file_path)])

    assert exit_code == OPERATION_CANCELLED
    assert "cancelada" in capsys.readouterr().out


def test_generate_from_openapi_file_yes_flag_skips_confirmation(offline_env, monkeypatch):
    file_path = _write_openapi_file(offline_env)
    monkeypatch.setattr(
        "builtins.input", lambda *a, **k: (_ for _ in ()).throw(AssertionError("não deveria perguntar"))
    )

    exit_code = main(["generate", "--openapi-file", str(file_path), "--yes"])

    assert exit_code == SUCCESS


# --- Segurança: nenhuma chamada de rede é feita ----------------------------------------------------------------


def test_generate_from_openapi_file_makes_no_network_calls(offline_env, postman_test_server):
    configure_server(postman_test_server)
    file_path = _write_openapi_file(offline_env)

    exit_code = main(["generate", "--openapi-file", str(file_path), "--yes"])

    assert exit_code == SUCCESS
    assert postman_test_server.received_paths == []


def test_generate_from_openapi_file_output_never_contains_a_leftover_api_key(
    offline_env, monkeypatch, capsys
):
    monkeypatch.setenv("POSTMAN_API_KEY", FAKE_API_KEY)
    file_path = _write_openapi_file(offline_env)

    exit_code = main(["generate", "--openapi-file", str(file_path), "--yes"])

    assert exit_code == SUCCESS
    captured = capsys.readouterr()
    assert FAKE_API_KEY not in captured.out
    assert FAKE_API_KEY not in captured.err
