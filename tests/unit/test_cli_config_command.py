import pytest

from api_quality_agent.cli.main import main


def test_config_show_reports_missing_api_key(monkeypatch, capsys):
    monkeypatch.delenv("POSTMAN_API_KEY", raising=False)

    exit_code = main(["config", "show"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "não configurada" in captured.out


def test_config_show_never_prints_raw_api_key(monkeypatch, capsys):
    fake_key = "P0STM4N-FAKE-KEY-1234567890"
    monkeypatch.setenv("POSTMAN_API_KEY", fake_key)

    exit_code = main(["config", "show"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert fake_key not in captured.out
    assert "configurada" in captured.out


def test_config_without_show_exits_with_invalid_input_code():
    with pytest.raises(SystemExit) as exc_info:
        main(["config"])
    assert exc_info.value.code == 2
