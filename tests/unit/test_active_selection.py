import pytest

from api_quality_agent.domain.exceptions import InputError
from api_quality_agent.domain.models import ActiveSelection


def test_creates_empty_selection():
    selection = ActiveSelection()
    assert selection.workspace_id is None
    assert selection.collection_id is None


def test_creates_full_selection():
    selection = ActiveSelection(workspace_id="ws-1", collection_id="col-1")
    assert selection.workspace_id == "ws-1"
    assert selection.collection_id == "col-1"


def test_workspace_and_collection_are_independent():
    # RN-002: Workspace e Collection são configurações independentes.
    selection = ActiveSelection(collection_id="col-1")
    assert selection.workspace_id is None
    assert selection.collection_id == "col-1"


def test_rejects_empty_workspace_id():
    with pytest.raises(InputError):
        ActiveSelection(workspace_id="", collection_id=None)


def test_rejects_empty_collection_id():
    with pytest.raises(InputError):
        ActiveSelection(workspace_id="ws-1", collection_id="")
