from api_quality_agent.application.use_cases import run_diagnostics


def test_passes_with_supported_python_version_and_accessible_directory(tmp_path):
    report = run_diagnostics(python_version=(3, 12, 1), working_directory=tmp_path)
    assert report.passed is True
    assert all(check.passed for check in report.checks)


def test_fails_with_unsupported_python_version(tmp_path):
    report = run_diagnostics(python_version=(3, 10, 0), working_directory=tmp_path)
    assert report.passed is False


def test_fails_with_missing_working_directory(tmp_path):
    missing_directory = tmp_path / "does-not-exist"
    report = run_diagnostics(python_version=(3, 12, 1), working_directory=missing_directory)
    assert report.passed is False
