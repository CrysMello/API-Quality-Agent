import json

import pytest

from api_quality_agent.adapters.config import FileSelectionRepository
from api_quality_agent.domain.exceptions import ConfigurationError
from api_quality_agent.domain.models import ActiveSelection


def test_load_returns_empty_selection_when_file_does_not_exist(tmp_path):
    repository = FileSelectionRepository(tmp_path / "selection.json")

    selection = repository.load()

    assert selection == ActiveSelection()


def test_save_then_load_round_trips_selection(tmp_path):
    repository = FileSelectionRepository(tmp_path / "selection.json")

    repository.save(ActiveSelection(workspace_id="ws-1", collection_id="col-1"))

    assert repository.load() == ActiveSelection(workspace_id="ws-1", collection_id="col-1")


def test_save_creates_parent_directories(tmp_path):
    nested_path = tmp_path / "nested" / "dir" / "selection.json"
    repository = FileSelectionRepository(nested_path)

    repository.save(ActiveSelection(workspace_id="ws-1"))

    assert nested_path.exists()


def test_saved_file_never_contains_api_key_or_secret_fields(tmp_path):
    path = tmp_path / "selection.json"
    repository = FileSelectionRepository(path)

    repository.save(ActiveSelection(workspace_id="ws-1", collection_id="col-1"))

    raw_text = path.read_text(encoding="utf-8")
    payload = json.loads(raw_text)
    assert set(payload.keys()) == {"workspace_id", "collection_id"}
    assert "api_key" not in raw_text.lower()
    assert "token" not in raw_text.lower()


def test_load_raises_configuration_error_for_corrupted_file(tmp_path):
    path = tmp_path / "selection.json"
    path.write_text("{ isto não é json", encoding="utf-8")
    repository = FileSelectionRepository(path)

    with pytest.raises(ConfigurationError):
        repository.load()


def test_load_raises_configuration_error_for_non_object_json(tmp_path):
    path = tmp_path / "selection.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    repository = FileSelectionRepository(path)

    with pytest.raises(ConfigurationError):
        repository.load()


def test_load_treats_empty_file_as_empty_selection(tmp_path):
    path = tmp_path / "selection.json"
    path.write_text("", encoding="utf-8")
    repository = FileSelectionRepository(path)

    assert repository.load() == ActiveSelection()
