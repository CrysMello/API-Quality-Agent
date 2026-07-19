import json
import sys
import tempfile
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


# --- Relatório vem do arquivo exportado, nunca do stdout ------------------------------------


def test_report_is_read_from_export_file_not_from_stdout(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "stdout_decoy")
    adapter = _build_adapter()

    result = adapter.run(collection_path=_minimal_collection(tmp_path))

    # O stdout contém um relatório "chamariz" com total_requests=999; o
    # resultado precisa vir do arquivo exportado (total_requests=1) — prova
    # de que o stdout nunca é tratado como fonte do relatório.
    assert result.total_requests == 1
    assert result.success is True


def test_fake_newman_does_not_print_report_json_to_stdout(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "success")
    adapter = _build_adapter()

    result = adapter.run(collection_path=_minimal_collection(tmp_path))

    assert '"stats"' not in result.stdout
    assert '"run"' not in result.stdout


# --- Ausência do relatório / arquivo vazio ---------------------------------------------------


def test_missing_report_file_is_reported_as_infrastructure_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "crash_no_output")
    adapter = _build_adapter()

    result = adapter.run(collection_path=_minimal_collection(tmp_path))

    assert result.infrastructure_failure is not None
    assert result.infrastructure_failure.failure_type == InfrastructureFailureType.UNEXPECTED_ERROR
    assert "não gerou" in result.infrastructure_failure.message.lower()


def test_empty_report_file_is_reported_as_infrastructure_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "empty_report")
    adapter = _build_adapter()

    result = adapter.run(collection_path=_minimal_collection(tmp_path))

    assert result.infrastructure_failure is not None
    assert result.infrastructure_failure.failure_type == InfrastructureFailureType.UNEXPECTED_ERROR
    assert "vazio" in result.infrastructure_failure.message.lower()


# --- Exit code diferente de zero, com stdout/stderr preservados -----------------------------


def test_non_zero_exit_code_is_preserved_alongside_stdout_and_stderr(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "test_failures")
    adapter = _build_adapter()

    result = adapter.run(collection_path=_minimal_collection(tmp_path))

    assert result.exit_code == 1
    assert result.infrastructure_failure is None
    assert isinstance(result.stdout, str)
    assert isinstance(result.stderr, str)


# --- Limpeza do diretório temporário ---------------------------------------------------------


def test_temporary_report_directory_is_removed_after_success(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "success")
    created_dirs: list[str] = []
    original_mkdtemp = tempfile.mkdtemp

    def _tracking_mkdtemp(*args, **kwargs):
        path = original_mkdtemp(*args, **kwargs)
        created_dirs.append(path)
        return path

    monkeypatch.setattr(tempfile, "mkdtemp", _tracking_mkdtemp)
    adapter = _build_adapter()

    adapter.run(collection_path=_minimal_collection(tmp_path))

    assert len(created_dirs) == 1
    assert not Path(created_dirs[0]).exists()


def test_temporary_report_directory_is_removed_even_on_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "invalid_report")
    created_dirs: list[str] = []
    original_mkdtemp = tempfile.mkdtemp

    def _tracking_mkdtemp(*args, **kwargs):
        path = original_mkdtemp(*args, **kwargs)
        created_dirs.append(path)
        return path

    monkeypatch.setattr(tempfile, "mkdtemp", _tracking_mkdtemp)
    adapter = _build_adapter()

    adapter.run(collection_path=_minimal_collection(tmp_path))

    assert len(created_dirs) == 1
    assert not Path(created_dirs[0]).exists()


# --- Caminho com espaços -----------------------------------------------------------------------


def test_works_with_collection_path_containing_spaces(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "success")
    spaced_dir = tmp_path / "pasta com espaços"
    spaced_dir.mkdir()
    collection_path = _write_json(
        spaced_dir,
        "collection.json",
        {
            "info": {
                "name": "Col",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": [],
        },
    )
    adapter = _build_adapter()

    result = adapter.run(collection_path=collection_path)

    assert result.success is True


# --- Nenhuma pasta newman/ criada no diretório de trabalho -----------------------------------


def test_no_newman_folder_is_created_in_current_working_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_NEWMAN_MODE", "success")
    monkeypatch.chdir(tmp_path)
    adapter = _build_adapter()

    adapter.run(collection_path=_minimal_collection(tmp_path))

    assert not (tmp_path / "newman").exists()
