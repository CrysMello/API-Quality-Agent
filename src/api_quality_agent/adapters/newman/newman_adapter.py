import json
import subprocess
import time
from pathlib import Path
from typing import Any

from api_quality_agent.domain.exceptions import InputError
from api_quality_agent.domain.models import (
    ExecutionResult,
    InfrastructureFailure,
    InfrastructureFailureType,
    TestFailure,
)
from api_quality_agent.domain.policies import ensure_non_empty_id
from api_quality_agent.ports.outbound.collection_runner import DEFAULT_RUN_TIMEOUT_SECONDS
from api_quality_agent.shared import mask_secret

DEFAULT_NEWMAN_EXECUTABLE = "newman"


class NewmanAdapter:
    def __init__(
        self,
        *,
        newman_executable: str = DEFAULT_NEWMAN_EXECUTABLE,
        command_prefix: tuple[str, ...] = (),
    ) -> None:
        # command_prefix existe apenas para permitir testes com um executável
        # de substituição real (nunca o Newman de verdade — ver
        # tests/fake_newman.py), sem depender de shell nem de mocks.
        ensure_non_empty_id(newman_executable, "newman_executable")
        self._executable = newman_executable
        self._command_prefix = command_prefix

    def run(
        self,
        *,
        collection_path: str,
        environment_path: str | None = None,
        timeout_seconds: float = DEFAULT_RUN_TIMEOUT_SECONDS,
    ) -> ExecutionResult:
        ensure_non_empty_id(collection_path, "collection_path")
        if environment_path is not None:
            ensure_non_empty_id(environment_path, "environment_path")
        if not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
            raise InputError("timeout_seconds deve ser um número maior que zero.")

        start = time.monotonic()

        # Validação local e determinística do arquivo de Collection, antes de
        # sequer iniciar o processo: evita depender de heurísticas sobre a
        # saída/stderr do Newman para saber se a Collection era inválida.
        collection_error = self._validate_collection_file(collection_path)
        if collection_error is not None:
            return _infrastructure_result(
                collection_path,
                InfrastructureFailureType.INVALID_COLLECTION,
                collection_error,
                duration=time.monotonic() - start,
            )

        secret_values = _extract_secret_values(environment_path)
        argv = [self._executable, *self._command_prefix, "run", collection_path, "--reporters", "json"]
        if environment_path is not None:
            argv += ["-e", environment_path]

        try:
            completed = subprocess.run(  # noqa: S603 - argv explícito, shell=False
                argv,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                shell=False,
            )
        except FileNotFoundError:
            return _infrastructure_result(
                collection_path,
                InfrastructureFailureType.EXECUTABLE_NOT_FOUND,
                f"Executável do Newman não encontrado: {self._executable!r}. "
                "Verifique se o Newman está instalado e no PATH, ou configure "
                "o caminho explícito do executável.",
                duration=time.monotonic() - start,
            )
        except subprocess.TimeoutExpired as exc:
            return _infrastructure_result(
                collection_path,
                InfrastructureFailureType.TIMEOUT,
                f"Execução do Newman excedeu o tempo limite de {timeout_seconds}s.",
                duration=time.monotonic() - start,
                stdout=_mask(_decode(exc.stdout), secret_values),
                stderr=_mask(_decode(exc.stderr), secret_values),
            )
        except OSError as exc:
            return _infrastructure_result(
                collection_path,
                InfrastructureFailureType.UNEXPECTED_ERROR,
                f"Falha inesperada ao iniciar o processo do Newman: {exc}",
                duration=time.monotonic() - start,
            )

        duration = time.monotonic() - start
        stdout = _mask(completed.stdout or "", secret_values)
        stderr = _mask(completed.stderr or "", secret_values)

        try:
            total_requests, total_assertions, failed_assertions, failures = _parse_report(
                completed.stdout or "", secret_values
            )
        except ValueError as exc:
            return ExecutionResult(
                collection_source=collection_path,
                success=False,
                exit_code=completed.returncode,
                duration_seconds=duration,
                total_requests=0,
                total_assertions=0,
                failed_assertions=0,
                test_failures=(),
                infrastructure_failure=InfrastructureFailure(
                    failure_type=InfrastructureFailureType.UNEXPECTED_ERROR,
                    message=f"Não foi possível interpretar o relatório do Newman: {exc}",
                ),
                stdout=stdout,
                stderr=stderr,
            )

        return ExecutionResult(
            collection_source=collection_path,
            success=completed.returncode == 0 and not failures,
            exit_code=completed.returncode,
            duration_seconds=duration,
            total_requests=total_requests,
            total_assertions=total_assertions,
            failed_assertions=failed_assertions,
            test_failures=failures,
            infrastructure_failure=None,
            stdout=stdout,
            stderr=stderr,
        )

    @staticmethod
    def _validate_collection_file(collection_path: str) -> str | None:
        try:
            raw_text = Path(collection_path).read_text(encoding="utf-8")
        except OSError as exc:
            return f"Não foi possível ler o arquivo da Collection ({collection_path!r}): {exc}"
        try:
            json.loads(raw_text)
        except json.JSONDecodeError as exc:
            return f"Collection não é um JSON válido ({collection_path!r}): {exc}"
        return None


def _infrastructure_result(
    collection_path: str,
    failure_type: InfrastructureFailureType,
    message: str,
    *,
    duration: float,
    stdout: str = "",
    stderr: str = "",
) -> ExecutionResult:
    return ExecutionResult(
        collection_source=collection_path,
        success=False,
        exit_code=None,
        duration_seconds=duration,
        total_requests=0,
        total_assertions=0,
        failed_assertions=0,
        test_failures=(),
        infrastructure_failure=InfrastructureFailure(failure_type=failure_type, message=message),
        stdout=stdout,
        stderr=stderr,
    )


def _decode(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _extract_secret_values(environment_path: str | None) -> tuple[str, ...]:
    # Postman marca variáveis de ambiente sensíveis com "type": "secret" —
    # usamos essa evidência estrutural (não o nome da variável) para saber
    # o que mascarar na saída do Newman.
    if environment_path is None:
        return ()
    try:
        raw = Path(environment_path).read_text(encoding="utf-8")
        data: Any = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return ()

    values = data.get("values") if isinstance(data, dict) else None
    if not isinstance(values, list):
        return ()

    secrets: list[str] = []
    for entry in values:
        if not isinstance(entry, dict) or entry.get("type") != "secret":
            continue
        value = entry.get("value")
        if isinstance(value, str) and value:
            secrets.append(value)
    return tuple(secrets)


def _mask(text: str, secret_values: tuple[str, ...]) -> str:
    masked = text
    for value in secret_values:
        masked = masked.replace(value, mask_secret(value))
    return masked


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_str(value: Any, default: str) -> str:
    return value if isinstance(value, str) else default


def _parse_report(
    raw_stdout: str, secret_values: tuple[str, ...]
) -> tuple[int, int, int, tuple[TestFailure, ...]]:
    try:
        payload = json.loads(raw_stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("saída do Newman não é um JSON válido") from exc

    run = _as_dict(payload).get("run")
    if not isinstance(run, dict):
        raise ValueError("relatório do Newman não possui a estrutura esperada ('run' ausente)")

    stats = _as_dict(run.get("stats"))
    requests_stats = _as_dict(stats.get("requests"))
    assertions_stats = _as_dict(stats.get("assertions"))

    total_requests = _safe_int(requests_stats.get("total"))
    total_assertions = _safe_int(assertions_stats.get("total"))
    failed_assertions = _safe_int(assertions_stats.get("failed"))

    failures_value = run.get("failures")
    raw_failures = failures_value if isinstance(failures_value, list) else []
    failures = []
    for raw_failure in raw_failures:
        if not isinstance(raw_failure, dict):
            continue
        source = _as_dict(raw_failure.get("source"))
        error = _as_dict(raw_failure.get("error"))
        request_name = source.get("name") if isinstance(source.get("name"), str) else None
        test_name = _as_str(error.get("test"), "desconhecido")
        message = _as_str(error.get("message"), "")
        failures.append(
            TestFailure(
                request_name=request_name,
                test_name=test_name,
                error_message=_mask(message, secret_values),
            )
        )

    return total_requests, total_assertions, failed_assertions, tuple(failures)


def _safe_int(value: Any) -> int:
    return value if isinstance(value, int) else 0
