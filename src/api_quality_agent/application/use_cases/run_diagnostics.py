import os
import sys
from dataclasses import dataclass
from pathlib import Path

MINIMUM_PYTHON_VERSION = (3, 12)


@dataclass(frozen=True)
class DiagnosticCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class DiagnosticReport:
    checks: list[DiagnosticCheck]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)


def run_diagnostics(
    *,
    python_version: tuple[int, int, int] | None = None,
    working_directory: Path | None = None,
) -> DiagnosticReport:
    version = (
        python_version
        if python_version is not None
        else (sys.version_info.major, sys.version_info.minor, sys.version_info.micro)
    )
    cwd = working_directory if working_directory is not None else Path.cwd()

    checks = [
        _check_python_version(version),
        _check_working_directory_access(cwd),
    ]
    return DiagnosticReport(checks=checks)


def _check_python_version(version: tuple[int, int, int]) -> DiagnosticCheck:
    passed = version[:2] >= MINIMUM_PYTHON_VERSION
    detail = (
        f"Python {'.'.join(map(str, version))} "
        f"(mínimo exigido: {'.'.join(map(str, MINIMUM_PYTHON_VERSION))})"
    )
    return DiagnosticCheck(name="Versão do Python", passed=passed, detail=detail)


def _check_working_directory_access(cwd: Path) -> DiagnosticCheck:
    accessible = cwd.exists() and os.access(cwd, os.R_OK | os.W_OK)
    detail = f"Diretório de trabalho: {cwd}"
    return DiagnosticCheck(name="Acesso ao diretório de trabalho", passed=accessible, detail=detail)
