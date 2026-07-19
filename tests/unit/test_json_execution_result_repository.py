import json
from datetime import datetime, timezone
from pathlib import Path

from api_quality_agent.adapters.filesystem import JsonExecutionResultRepository

_FIXED_MOMENT = datetime(2026, 7, 20, 10, 35, 12, 123456, tzinfo=timezone.utc)


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_save_creates_timestamped_directory_with_result_json(tmp_path):
    repository = JsonExecutionResultRepository(tmp_path, clock=lambda: _FIXED_MOMENT)

    location = repository.save(content='{"success": true}')

    saved_path = tmp_path / "run_20260720_103512123456" / "result.json"
    assert saved_path.is_file()
    assert location.path == str(saved_path)


def test_save_preserves_content_exactly(tmp_path):
    repository = JsonExecutionResultRepository(tmp_path, clock=lambda: _FIXED_MOMENT)
    payload = json.dumps({"success": True, "summary": {"requests": 3}}, indent=2)

    location = repository.save(content=payload)

    assert _read(location.path) == payload


def test_two_saves_with_the_same_second_produce_different_directories(tmp_path):
    moments = iter(
        [
            datetime(2026, 7, 20, 10, 35, 12, 100000, tzinfo=timezone.utc),
            datetime(2026, 7, 20, 10, 35, 12, 200000, tzinfo=timezone.utc),
        ]
    )
    repository = JsonExecutionResultRepository(tmp_path, clock=lambda: next(moments))

    first = repository.save(content="{}")
    second = repository.save(content="{}")

    assert first.path != second.path


def test_does_not_overwrite_previous_executions(tmp_path):
    moments = iter(
        [
            datetime(2026, 7, 20, 10, 35, 12, 0, tzinfo=timezone.utc),
            datetime(2026, 7, 20, 10, 36, 0, 0, tzinfo=timezone.utc),
        ]
    )
    repository = JsonExecutionResultRepository(tmp_path, clock=lambda: next(moments))

    first = repository.save(content='{"run": 1}')
    second = repository.save(content='{"run": 2}')

    assert _read(first.path) == '{"run": 1}'
    assert _read(second.path) == '{"run": 2}'


def test_default_base_path_is_artifacts(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    repository = JsonExecutionResultRepository(clock=lambda: _FIXED_MOMENT)

    location = repository.save(content="{}")

    assert location.path.startswith("artifacts")
