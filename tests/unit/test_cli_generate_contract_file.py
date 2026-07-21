import json

import openpyxl
import pytest
from conftest import FAKE_API_KEY

from api_quality_agent.cli.exit_codes import FUNCTIONAL_FAILURE, INVALID_INPUT_OR_CONFIGURATION, SUCCESS
from api_quality_agent.cli.main import main

_HEADER_ROW = ["Sequencial", "Nome do campo", "Formato", "Tamanho", "Obrigatoriedade", "Regras (Domínio)"]


def _write_contract_file(path, *, method="GET", uri="/v2/pet/{{petId}}"):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Planilha1"
    rows = [
        ["URI", uri],
        ["Método", method],
        ["Resposta caso HTTP Status code 200 - OK"],
        _HEADER_ROW,
        ["1", "dado", "Objeto", None, "SIM"],
        ["1.1", "id", "Alfanumerico", 10, "SIM"],
    ]
    for row in rows:
        sheet.append(row)
    file_path = path / "contrato.xlsx"
    workbook.save(file_path)
    return file_path


def _write_collection_file(path, *, name="Pets"):
    document = {
        "info": {
            "name": name,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": [
            {
                "name": "Buscar pet",
                "id": "req-1",
                "request": {"method": "GET", "url": "https://api.exemplo.com/v2/pet/:petId"},
                "response": [
                    {"name": "ok", "status": "OK", "code": 200, "header": [], "body": "{}"}
                ],
            }
        ],
    }
    file_path = path / "collection.json"
    file_path.write_text(json.dumps(document), encoding="utf-8")
    return file_path


def test_generate_from_file_with_contract_file_saves_scripts_without_api_key(offline_env, capsys):
    collection_path = _write_collection_file(offline_env)
    contract_path = _write_contract_file(offline_env)

    exit_code = main(
        [
            "generate",
            "--file",
            str(collection_path),
            "--contract-file",
            str(contract_path),
            "--yes",
        ]
    )

    assert exit_code == SUCCESS
    out = capsys.readouterr().out
    assert "Endpoints processados: 1" in out


def test_generate_from_file_with_contract_file_never_requires_api_key(offline_env, monkeypatch):
    monkeypatch.delenv("POSTMAN_API_KEY", raising=False)
    collection_path = _write_collection_file(offline_env)
    contract_path = _write_contract_file(offline_env)

    exit_code = main(
        ["generate", "--file", str(collection_path), "--contract-file", str(contract_path), "--yes"]
    )

    assert exit_code == SUCCESS


def test_generate_rejects_contract_file_and_openapi_file_together(offline_env):
    collection_path = _write_collection_file(offline_env)
    contract_path = _write_contract_file(offline_env)

    exit_code = main(
        [
            "generate",
            "--openapi-file",
            str(collection_path),
            "--contract-file",
            str(contract_path),
            "--yes",
        ]
    )

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


def test_generate_from_file_without_contract_file_behavior_is_unchanged(offline_env, capsys):
    collection_path = _write_collection_file(offline_env)

    exit_code = main(["generate", "--file", str(collection_path), "--yes"])

    assert exit_code == SUCCESS
    out = capsys.readouterr().out
    assert "Endpoints processados: 1" in out


def test_generate_from_file_with_contract_file_makes_no_network_calls(
    offline_env, postman_test_server
):
    collection_path = _write_collection_file(offline_env)
    contract_path = _write_contract_file(offline_env)

    exit_code = main(
        ["generate", "--file", str(collection_path), "--contract-file", str(contract_path), "--yes"]
    )

    assert exit_code == SUCCESS
    assert postman_test_server.received_paths == []


def test_generate_from_file_with_contract_file_saves_a_match_report(offline_env, capsys):
    collection_path = _write_collection_file(offline_env)
    contract_path = _write_contract_file(offline_env)

    exit_code = main(
        ["generate", "--file", str(collection_path), "--contract-file", str(contract_path), "--yes"]
    )

    assert exit_code == SUCCESS
    out = capsys.readouterr().out
    assert "contract-match-report.json" in out
    assert "contract-match-report.html" in out

    report_dir = offline_env / "artifacts" / "local"
    json_reports = list(report_dir.rglob("contract-match-report.json"))
    html_reports = list(report_dir.rglob("contract-match-report.html"))
    assert len(json_reports) == 1
    assert len(html_reports) == 1

    payload = json.loads(json_reports[0].read_text(encoding="utf-8"))
    assert payload["summary"]["matched"] == 1


def test_generate_from_file_with_contract_file_output_never_contains_a_leftover_api_key(
    offline_env, monkeypatch, capsys
):
    monkeypatch.setenv("POSTMAN_API_KEY", FAKE_API_KEY)
    collection_path = _write_collection_file(offline_env)
    contract_path = _write_contract_file(offline_env)

    exit_code = main(
        ["generate", "--file", str(collection_path), "--contract-file", str(contract_path), "--yes"]
    )

    assert exit_code == SUCCESS
    captured = capsys.readouterr()
    assert FAKE_API_KEY not in captured.out
    assert FAKE_API_KEY not in captured.err


# Correção dos exit codes: arquivo de contrato inexistente/vazio/corrompido
# deve resultar no código de saída 2 (entrada inválida), não no código 8
# (erro inesperado) que era retornado antes desta correção.


def test_generate_with_nonexistent_contract_file_returns_invalid_input_exit_code(offline_env, capsys):
    collection_path = _write_collection_file(offline_env)
    missing_contract_path = offline_env / "nao_existe.xlsx"

    exit_code = main(
        [
            "generate",
            "--file",
            str(collection_path),
            "--contract-file",
            str(missing_contract_path),
            "--yes",
        ]
    )

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION
    assert "Erro inesperado" not in capsys.readouterr().out


def test_generate_with_empty_contract_file_returns_invalid_input_exit_code(offline_env, capsys):
    collection_path = _write_collection_file(offline_env)
    empty_contract_path = offline_env / "vazio.xlsx"
    empty_contract_path.write_bytes(b"")

    exit_code = main(
        [
            "generate",
            "--file",
            str(collection_path),
            "--contract-file",
            str(empty_contract_path),
            "--yes",
        ]
    )

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION
    assert "Erro inesperado" not in capsys.readouterr().out


def test_generate_with_corrupted_contract_file_returns_invalid_input_exit_code(offline_env, capsys):
    collection_path = _write_collection_file(offline_env)
    corrupted_contract_path = offline_env / "corrompido.xlsx"
    corrupted_contract_path.write_bytes(b"isto nao e um arquivo zip valido")

    exit_code = main(
        [
            "generate",
            "--file",
            str(collection_path),
            "--contract-file",
            str(corrupted_contract_path),
            "--yes",
        ]
    )

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION
    assert "Erro inesperado" not in capsys.readouterr().out


# --collection-path-prefix: prefixo fixo de path (ex.: gateway) presente só
# nas requests da Collection, ausente do path declarado no contrato.


def _write_collection_file_with_prefix(path, *, prefix, name="Pets"):
    document = {
        "info": {
            "name": name,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": [
            {
                "name": "Buscar pet",
                "id": "req-1",
                "request": {
                    "method": "GET",
                    "url": f"https://api.exemplo.com{prefix}/v2/pet/:petId",
                },
                "response": [
                    {"name": "ok", "status": "OK", "code": 200, "header": [], "body": "{}"}
                ],
            }
        ],
    }
    file_path = path / "collection.json"
    file_path.write_text(json.dumps(document), encoding="utf-8")
    return file_path


def test_generate_without_collection_path_prefix_reports_not_found_when_collection_has_gateway_prefix(
    offline_env, capsys
):
    collection_path = _write_collection_file_with_prefix(offline_env, prefix="/api")
    contract_path = _write_contract_file(offline_env, uri="/v2/pet/{{petId}}")

    exit_code = main(
        ["generate", "--file", str(collection_path), "--contract-file", str(contract_path), "--yes"]
    )

    assert exit_code == SUCCESS
    report_dir = offline_env / "artifacts" / "local"
    payload = json.loads(next(report_dir.rglob("contract-match-report.json")).read_text(encoding="utf-8"))
    assert payload["summary"]["not_found"] == 1


def test_generate_with_collection_path_prefix_matches_the_declared_contract(offline_env, capsys):
    collection_path = _write_collection_file_with_prefix(offline_env, prefix="/api")
    contract_path = _write_contract_file(offline_env, uri="/v2/pet/{{petId}}")

    exit_code = main(
        [
            "generate",
            "--file",
            str(collection_path),
            "--contract-file",
            str(contract_path),
            "--collection-path-prefix",
            "/api",
            "--yes",
        ]
    )

    assert exit_code == SUCCESS
    report_dir = offline_env / "artifacts" / "local"
    payload = json.loads(next(report_dir.rglob("contract-match-report.json")).read_text(encoding="utf-8"))
    assert payload["summary"]["matched"] == 1


def test_generate_rejects_collection_path_prefix_without_contract_file(offline_env):
    collection_path = _write_collection_file(offline_env)

    exit_code = main(
        [
            "generate",
            "--file",
            str(collection_path),
            "--collection-path-prefix",
            "/api",
            "--yes",
        ]
    )

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


def test_generate_rejects_collection_path_prefix_with_no_usable_segment(offline_env):
    collection_path = _write_collection_file(offline_env)
    contract_path = _write_contract_file(offline_env)

    exit_code = main(
        [
            "generate",
            "--file",
            str(collection_path),
            "--contract-file",
            str(contract_path),
            "--collection-path-prefix",
            "////",
            "--yes",
        ]
    )

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


# --strict-contract-match: processa todos os endpoints e persiste o
# Contract Match Report normalmente; só depois decide falhar (exit code 1)
# se houver UNMATCHED/AMBIGUOUS.


def test_generate_strict_contract_match_succeeds_when_everything_is_matched(offline_env, capsys):
    collection_path = _write_collection_file(offline_env)
    contract_path = _write_contract_file(offline_env)

    exit_code = main(
        [
            "generate",
            "--file",
            str(collection_path),
            "--contract-file",
            str(contract_path),
            "--strict-contract-match",
            "--yes",
        ]
    )

    assert exit_code == SUCCESS
    assert "Processo concluído com sucesso" in capsys.readouterr().out


def test_generate_strict_contract_match_fails_with_functional_failure_exit_code_when_unmatched(
    offline_env, capsys
):
    collection_path = _write_collection_file(offline_env)
    contract_path = _write_contract_file(offline_env, uri="/v2/outra-coisa")

    exit_code = main(
        [
            "generate",
            "--file",
            str(collection_path),
            "--contract-file",
            str(contract_path),
            "--strict-contract-match",
            "--yes",
        ]
    )

    assert exit_code == FUNCTIONAL_FAILURE
    captured = capsys.readouterr()
    assert "Processo concluído com sucesso" not in captured.out
    assert "Contract Match Summary" in captured.err
    assert "Unmatched: 1" in captured.err

    # O relatório precisa existir em disco mesmo com o comando falhando.
    report_dir = offline_env / "artifacts" / "local"
    json_reports = list(report_dir.rglob("contract-match-report.json"))
    html_reports = list(report_dir.rglob("contract-match-report.html"))
    assert len(json_reports) == 1
    assert len(html_reports) == 1
    payload = json.loads(json_reports[0].read_text(encoding="utf-8"))
    assert payload["summary"]["not_found"] == 1


def test_generate_without_strict_contract_match_succeeds_even_with_unmatched_endpoints(
    offline_env, capsys
):
    collection_path = _write_collection_file(offline_env)
    contract_path = _write_contract_file(offline_env, uri="/v2/outra-coisa")

    exit_code = main(
        ["generate", "--file", str(collection_path), "--contract-file", str(contract_path), "--yes"]
    )

    assert exit_code == SUCCESS
    assert "Processo concluído com sucesso" in capsys.readouterr().out


def test_generate_rejects_strict_contract_match_without_contract_file(offline_env):
    collection_path = _write_collection_file(offline_env)

    exit_code = main(
        ["generate", "--file", str(collection_path), "--strict-contract-match", "--yes"]
    )

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION
