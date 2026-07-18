from api_quality_agent.application.use_cases import DiagnosticCheck, DiagnosticReport
from api_quality_agent.cli.main import main


def test_doctor_succeeds_in_healthy_environment(capsys):
    exit_code = main(["doctor"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "OK" in captured.out


def test_doctor_reports_failure_and_exit_code_one(monkeypatch, capsys):
    failing_report = DiagnosticReport(
        checks=[DiagnosticCheck(name="Verificação simulada", passed=False, detail="detalhe simulado")]
    )
    monkeypatch.setattr(
        "api_quality_agent.cli.commands.doctor_command.run_diagnostics",
        lambda: failing_report,
    )

    exit_code = main(["doctor"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "FALHA" in captured.out
    assert "detalhe simulado" in captured.out
