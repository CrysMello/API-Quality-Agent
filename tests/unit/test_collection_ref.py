import dataclasses

import pytest

from api_quality_agent.domain.exceptions import InputError
from api_quality_agent.domain.models import CollectionRef


def test_creates_valid_collection_ref():
    collection = CollectionRef(id="col-1", name="Collection 1", workspace_id="ws-1")
    assert collection.id == "col-1"
    assert collection.name == "Collection 1"
    assert collection.workspace_id == "ws-1"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"id": "", "name": "Collection", "workspace_id": "ws-1"},
        {"id": "col-1", "name": "", "workspace_id": "ws-1"},
        {"id": "col-1", "name": "Collection", "workspace_id": ""},
        {"id": "col-1", "name": "Collection", "workspace_id": "   "},
    ],
)
def test_rejects_empty_fields(kwargs):
    with pytest.raises(InputError):
        CollectionRef(**kwargs)


def test_collection_ref_is_immutable():
    collection = CollectionRef(id="col-1", name="Collection 1", workspace_id="ws-1")
    with pytest.raises(dataclasses.FrozenInstanceError):
        collection.workspace_id = "ws-2"
