import json

import pytest
from conftest import COLLECTION_A_ID, FAKE_API_KEY, configure_server

from api_quality_agent.cli.exit_codes import (
    INVALID_INPUT_OR_CONFIGURATION,
    OPERATION_CANCELLED,
    SUCCESS,
)
from api_quality_agent.cli.main import main


def _write_collection_file(path, *, name="Collection Local"):
    document = {
        "info": {
            "name": name,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": [
            {
                "name": "Criar pet",
                "id": "req-1",
                "request": {"method": "POST", "url": "https://api.exemplo.com/pets"},
                "response": [
                    {"name": "ok", "status": "Created", "code": 201, "header": [], "body": "{}"}
                ],
            }
        ],
    }
    file_path = path / "collection.json"
    file_path.write_text(json.dumps(document), encoding="utf-8")
    return file_path


# --- Fluxo feliz, sem API Key ----------------------------------------------------------------


def test_generate_from_file_succeeds_without_api_key(offline_env, capsys):
    file_path = _write_collection_file(offline_env)

    exit_code = main(["generate", "--file", str(file_path), "--yes"])

    assert exit_code == SUCCESS
    out = capsys.readouterr().out
    assert "Collection Local" in out
    assert "Endpoints processados: 1" in out


def test_generate_from_file_never_requires_postman_api_key_env_var(
    offline_env, monkeypatch, capsys
):
    monkeypatch.delenv("POSTMAN_API_KEY", raising=False)
    file_path = _write_collection_file(offline_env)

    exit_code = main(["generate", "--file", str(file_path), "--yes"])

    assert exit_code == SUCCESS


def test_generate_from_file_saves_artifacts_under_local_workspace(offline_env):
    file_path = _write_collection_file(offline_env, name="Minha Collection")

    exit_code = main(["generate", "--file", str(file_path), "--yes"])

    assert exit_code == SUCCESS
    artifacts_dir = offline_env / "artifacts" / "local"
    assert artifacts_dir.is_dir()


# --- Arquivo inválido ----------------------------------------------------------------


def test_generate_from_file_with_missing_file_reports_invalid_input(offline_env, capsys):
    missing_path = offline_env / "nao_existe.json"

    exit_code = main(["generate", "--file", str(missing_path), "--yes"])

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION
    assert "encontrado" in capsys.readouterr().err.lower()


def test_generate_from_file_with_invalid_json_reports_invalid_input(offline_env, capsys):
    file_path = offline_env / "invalido.json"
    file_path.write_text("{ isso não é json válido", encoding="utf-8")

    exit_code = main(["generate", "--file", str(file_path), "--yes"])

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


def test_generate_from_file_with_non_json_extension_reports_invalid_input(offline_env, capsys):
    file_path = offline_env / "collection.txt"
    file_path.write_text("{}", encoding="utf-8")

    exit_code = main(["generate", "--file", str(file_path), "--yes"])

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


def test_generate_from_file_with_empty_file_reports_invalid_input(offline_env, capsys):
    file_path = offline_env / "vazio.json"
    file_path.write_text("", encoding="utf-8")

    exit_code = main(["generate", "--file", str(file_path), "--yes"])

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


def test_generate_from_file_with_valid_json_but_not_a_collection_reports_invalid_input(
    offline_env, capsys
):
    file_path = offline_env / "nao_e_collection.json"
    file_path.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")

    exit_code = main(["generate", "--file", str(file_path), "--yes"])

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


# --- Conflitos com outras formas de seleção ----------------------------------------------------------------


def test_generate_rejects_file_and_collection_id_together(offline_env):
    file_path = _write_collection_file(offline_env)

    exit_code = main(
        ["generate", "--file", str(file_path), "--collection-id", COLLECTION_A_ID, "--yes"]
    )

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


def test_generate_rejects_file_and_collection_name_together(offline_env):
    file_path = _write_collection_file(offline_env)

    exit_code = main(
        ["generate", "--file", str(file_path), "--collection-name", "Qualquer", "--yes"]
    )

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


def test_generate_rejects_file_and_index_together(offline_env):
    file_path = _write_collection_file(offline_env)

    exit_code = main(["generate", "1", "--file", str(file_path), "--yes"])

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


# --- Confirmação ----------------------------------------------------------------


def test_generate_from_file_confirmation_declined_cancels(offline_env, monkeypatch, capsys):
    file_path = _write_collection_file(offline_env)
    monkeypatch.setattr("builtins.input", lambda *_: "n")

    exit_code = main(["generate", "--file", str(file_path)])

    assert exit_code == OPERATION_CANCELLED
    assert "cancelada" in capsys.readouterr().out


def test_generate_from_file_yes_flag_skips_confirmation(offline_env, monkeypatch):
    file_path = _write_collection_file(offline_env)
    monkeypatch.setattr(
        "builtins.input", lambda *a, **k: (_ for _ in ()).throw(AssertionError("não deveria perguntar"))
    )

    exit_code = main(["generate", "--file", str(file_path), "--yes"])

    assert exit_code == SUCCESS


# --- Segurança: nenhuma chamada de rede é feita ----------------------------------------------------------------


def test_generate_from_file_makes_no_network_calls(offline_env, postman_test_server):
    configure_server(postman_test_server)
    file_path = _write_collection_file(offline_env)

    exit_code = main(["generate", "--file", str(file_path), "--yes"])

    assert exit_code == SUCCESS
    assert postman_test_server.received_paths == []


def test_generate_from_file_output_never_contains_a_leftover_api_key(offline_env, monkeypatch, capsys):
    monkeypatch.setenv("POSTMAN_API_KEY", FAKE_API_KEY)
    file_path = _write_collection_file(offline_env)

    exit_code = main(["generate", "--file", str(file_path), "--yes"])

    assert exit_code == SUCCESS
    captured = capsys.readouterr()
    assert FAKE_API_KEY not in captured.out
    assert FAKE_API_KEY not in captured.err
