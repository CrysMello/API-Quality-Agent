import argparse

from api_quality_agent.application.use_cases import run_diagnostics


def register(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    doctor_parser = subparsers.add_parser(
        "doctor", help="Valida pré-requisitos locais do ambiente."
    )
    doctor_parser.set_defaults(handler=_handle_doctor)


def _handle_doctor(_args: argparse.Namespace) -> int:
    report = run_diagnostics()
    for check in report.checks:
        status = "OK" if check.passed else "FALHA"
        print(f"[{status}] {check.name}: {check.detail}")
    return 0 if report.passed else 1
