import json
import os
import sys
import time


def main() -> int:
    mode = os.environ.get("FAKE_NEWMAN_MODE", "success")

    if mode == "slow":
        time.sleep(float(os.environ.get("FAKE_NEWMAN_SLEEP_SECONDS", "5")))

    if mode == "stderr_only":
        sys.stderr.write("erro simulado do newman no stderr\n")
        return 1

    if mode == "crash_no_output":
        return 2

    if mode == "invalid_report":
        sys.stdout.write("isto não é um relatório JSON válido")
        return 1

    report = _build_report(mode)
    sys.stdout.write(json.dumps(report))
    return 0 if mode == "success" else 1


def _build_report(mode: str) -> dict:
    secret_value = os.environ.get("FAKE_NEWMAN_SECRET_VALUE", "")

    if mode == "success":
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
