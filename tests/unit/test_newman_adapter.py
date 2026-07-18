import json
import sys
from pathlib import Path

import pytest

from api_quality_agent.adapters.newman import NewmanAdapter
from api_quality_agent.domain.exceptions import InputError
from api_quality_agent.domain.models import InfrastructureFailureType

FAKE_NEWMAN_SCRIPT = Path(__file__).resolve().parent.parent / "fake_newman.py"


def _build_adapter(**overrides) -> NewmanAdapter:
    params = {
        "newman_executable": sys.executable,
        "command_prefix": (str(FAKE_NEWMAN_SCRIPT),),
    }
    params.update(overrides)
    return NewmanAdapter(**params)


def _write_json(tmp_path: Path, name: str, content: dict) -> str:
    path = tmp_path / name
    path.write_text(json.dumps(content), encoding="utf-8")
    return str(path)


def _write_text(tmp_path: Path, name: str, content: str) -> str:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return str(path)


def _minimal_collection(tmp_path: Path) -> str:
    return _write_json(
        tmp_path,
        "collection.json",
        {
            "info": {
                "name": "Col",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": [],
        },
    )


# --- Sucesso -----------------------------------------------------------------------------


def test_success_run_returns_successful_result(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "success")
    adapter = _build_adapter()

    result = adapter.run(collection_path=_minimal_collection(tmp_path))

    assert result.success is True
    assert result.exit_code == 0
    assert result.infrastructure_failure is None
    assert result.test_failures == ()
    assert result.total_requests == 1
    assert result.failed_assertions == 0
    assert result.duration_seconds >= 0.0


# --- Testes reprovados ---------------------------------------------------------------------


def test_failed_tests_are_captured_without_infrastructure_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "test_failures")
    adapter = _build_adapter()

    result = adapter.run(collection_path=_minimal_collection(tmp_path))

    assert result.success is False
    assert result.infrastructure_failure is None  # reprovação de teste não é falha de infra
    assert len(result.test_failures) == 1
    failure = result.test_failures[0]
    assert failure.request_name == "Criar pet"
    assert failure.test_name == "Status code é 201"
    assert "expected 500 to equal 201" in failure.error_message


# --- Executável ausente ---------------------------------------------------------------------


def test_missing_executable_returns_infrastructure_failure(tmp_path):
    adapter = NewmanAdapter(newman_executable="este-executavel-nao-existe-xyz")

    result = adapter.run(collection_path=_minimal_collection(tmp_path))

    assert result.success is False
    assert result.exit_code is None
    assert result.infrastructure_failure is not None
    assert result.infrastructure_failure.failure_type == InfrastructureFailureType.EXECUTABLE_NOT_FOUND


# --- Timeout -----------------------------------------------------------------------------


def test_timeout_returns_infrastructure_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "slow")
    monkeypatch.setenv("FAKE_NEWMAN_SLEEP_SECONDS", "5")
    adapter = _build_adapter()

    result = adapter.run(collection_path=_minimal_collection(tmp_path), timeout_seconds=0.3)

    assert result.success is False
    assert result.exit_code is None
    assert result.infrastructure_failure is not None
    assert result.infrastructure_failure.failure_type == InfrastructureFailureType.TIMEOUT


# --- stderr ------------------------------------------------------------------------------


def test_stderr_is_captured(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "stderr_only")
    adapter = _build_adapter()

    result = adapter.run(collection_path=_minimal_collection(tmp_path))

    assert "erro simulado do newman no stderr" in result.stderr


# --- Collection inválida ------------------------------------------------------------------


def test_invalid_collection_json_is_detected_before_spawning_process(tmp_path):
    invalid_path = _write_text(tmp_path, "invalid.json", "isto não é json")
    # executável propositalmente inexistente: se o processo fosse mesmo
    # iniciado, o resultado seria EXECUTABLE_NOT_FOUND, não INVALID_COLLECTION
    adapter = NewmanAdapter(newman_executable="este-executavel-nao-existe-xyz")

    result = adapter.run(collection_path=invalid_path)

    assert result.infrastructure_failure is not None
    assert result.infrastructure_failure.failure_type == InfrastructureFailureType.INVALID_COLLECTION


def test_missing_collection_file_is_detected_before_spawning_process(tmp_path):
    adapter = NewmanAdapter(newman_executable="este-executavel-nao-existe-xyz")

    result = adapter.run(collection_path=str(tmp_path / "nao-existe.json"))

    assert result.infrastructure_failure is not None
    assert result.infrastructure_failure.failure_type == InfrastructureFailureType.INVALID_COLLECTION


# --- Falha de infraestrutura genérica (relatório ilegível) ---------------------------------


def test_unparsable_report_is_reported_as_infrastructure_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "invalid_report")
    adapter = _build_adapter()

    result = adapter.run(collection_path=_minimal_collection(tmp_path))

    assert result.infrastructure_failure is not None
    assert result.infrastructure_failure.failure_type == InfrastructureFailureType.UNEXPECTED_ERROR


# --- Argumentos --------------------------------------------------------------------------


def test_rejects_empty_collection_path():
    adapter = _build_adapter()

    with pytest.raises(InputError):
        adapter.run(collection_path="")


def test_rejects_empty_environment_path(tmp_path):
    adapter = _build_adapter()

    with pytest.raises(InputError):
        adapter.run(collection_path=_minimal_collection(tmp_path), environment_path="")


def test_rejects_non_positive_timeout(tmp_path):
    adapter = _build_adapter()

    with pytest.raises(InputError):
        adapter.run(collection_path=_minimal_collection(tmp_path), timeout_seconds=0)


def test_rejects_empty_newman_executable():
    with pytest.raises(InputError):
        NewmanAdapter(newman_executable="")


# --- Environment opcional ------------------------------------------------------------------


def test_environment_is_not_passed_when_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "success")
    adapter = _build_adapter()

    result = adapter.run(collection_path=_minimal_collection(tmp_path))

    assert result.success is True  # roda normalmente sem -e, sem seleção implícita


def test_environment_path_is_forwarded_when_provided(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "success")
    environment_path = _write_json(tmp_path, "env.json", {"values": []})
    adapter = _build_adapter()

    result = adapter.run(
        collection_path=_minimal_collection(tmp_path), environment_path=environment_path
    )

    assert result.success is True


# --- Mascaramento de segredos --------------------------------------------------------------


def test_secret_environment_values_are_masked_in_test_failure_message(tmp_path, monkeypatch):
    secret_value = "sk_live_super_secret_token_123456"
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "test_failures_with_secret")
    monkeypatch.setenv("FAKE_NEWMAN_SECRET_VALUE", secret_value)
    environment_path = _write_json(
        tmp_path,
        "env.json",
        {"values": [{"key": "token", "value": secret_value, "type": "secret"}]},
    )
    adapter = _build_adapter()

    result = adapter.run(
        collection_path=_minimal_collection(tmp_path), environment_path=environment_path
    )

    assert secret_value not in result.stdout
    assert secret_value not in result.stderr
    assert all(secret_value not in failure.error_message for failure in result.test_failures)
    # o valor mascarado (prefixo/sufixo visíveis) ainda aparece, provando que
    # a mensagem não foi simplesmente removida
    assert any("****" in failure.error_message for failure in result.test_failures)


def test_non_secret_environment_values_are_not_masked(tmp_path, monkeypatch):
    public_value = "valor-publico-sem-risco"
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "test_failures_with_secret")
    monkeypatch.setenv("FAKE_NEWMAN_SECRET_VALUE", public_value)
    environment_path = _write_json(
        tmp_path,
        "env.json",
        {"values": [{"key": "base_url", "value": public_value, "type": "default"}]},
    )
    adapter = _build_adapter()

    result = adapter.run(
        collection_path=_minimal_collection(tmp_path), environment_path=environment_path
    )

    assert any(public_value in failure.error_message for failure in result.test_failures)


# --- Processo simulado (subprocess real, nunca o Newman de verdade) ------------------------


def test_uses_a_real_subprocess_with_real_elapsed_time(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "slow")
    monkeypatch.setenv("FAKE_NEWMAN_SLEEP_SECONDS", "0.2")
    adapter = _build_adapter()

    result = adapter.run(collection_path=_minimal_collection(tmp_path), timeout_seconds=5)

    assert result.duration_seconds >= 0.15
    assert result.infrastructure_failure is None  # completou normalmente, após o sleep real
