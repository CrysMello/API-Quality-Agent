import json
import os
import sys
import time


def _extract_export_path(argv: list) -> str | None:
    for index, arg in enumerate(argv):
        if arg == "--reporter-json-export" and index + 1 < len(argv):
            return argv[index + 1]
    return None


def main() -> int:
    mode = os.environ.get("FAKE_NEWMAN_MODE", "success")
    export_path = _extract_export_path(sys.argv)

    if mode == "slow":
        time.sleep(float(os.environ.get("FAKE_NEWMAN_SLEEP_SECONDS", "5")))

    if mode == "stderr_only":
        # Simula uma falha antes de o Newman conseguir escrever o relatório:
        # nenhum arquivo é gerado no caminho de export.
        sys.stderr.write("erro simulado do newman no stderr\n")
        return 1

    if mode == "crash_no_output":
        # Nenhum stdout/stderr/arquivo — simula um crash abrupto do processo.
        return 2

    if mode == "invalid_report":
        # O Newman real também pode deixar um arquivo corrompido/incompleto
        # no caminho de export em caso de falha durante a escrita.
        if export_path:
            with open(export_path, "w", encoding="utf-8") as handle:
                handle.write("isto não é um relatório JSON válido")
        return 1

    if mode == "empty_report":
        if export_path:
            open(export_path, "w", encoding="utf-8").close()
        return 1

    report = _build_report(mode)

    if mode == "stdout_decoy":
        # Prova de que o stdout nunca é tratado como fonte do relatório: aqui
        # ele contém um JSON "chamariz", propositalmente diferente do
        # relatório real gravado no arquivo de export.
        decoy_report = _build_report("success")
        decoy_report["run"]["stats"]["requests"]["total"] = 999
        sys.stdout.write(json.dumps(decoy_report))
    else:
        # Newman real: stdout traz só mensagens de progresso do CLI, nunca o
        # relatório JSON em si (esse vai exclusivamente para o arquivo).
        sys.stdout.write("newman: execução concluída\n")

    if export_path:
        with open(export_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle)

    return 0 if mode in ("success", "stdout_decoy") else 1


def _build_report(mode: str) -> dict:
    secret_value = os.environ.get("FAKE_NEWMAN_SECRET_VALUE", "")

    if mode in ("success", "stdout_decoy"):
        failures = []
        assertions_failed = 0
    else:
        message = "expected 500 to equal 201"
        if mode == "test_failures_with_secret" and secret_value:
            message = f"expected response body to contain token {secret_value}"
        failures = [
            {
                "source": {"name": "Criar pet"},
                "error": {
                    "name": "AssertionError",
                    "test": "Status code é 201",
                    "message": message,
                },
            }
        ]
        assertions_failed = 1

    return {
        "run": {
            "stats": {
                "requests": {"total": 1, "failed": 0},
                "assertions": {"total": 1, "failed": assertions_failed},
            },
            "timings": {"started": 1000, "completed": 1200},
            "failures": failures,
        }
    }


if __name__ == "__main__":
    sys.exit(main())
