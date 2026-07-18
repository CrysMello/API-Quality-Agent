import dataclasses

import pytest

from api_quality_agent.domain.exceptions import InputError
from api_quality_agent.domain.models import WorkspaceRef


def test_creates_valid_workspace_ref():
    workspace = WorkspaceRef(id="ws-1", name="Workspace 1")
    assert workspace.id == "ws-1"
    assert workspace.name == "Workspace 1"


def test_rejects_empty_id():
    with pytest.raises(InputError):
        WorkspaceRef(id="", name="Workspace 1")


def test_rejects_whitespace_name():
    with pytest.raises(InputError):
        WorkspaceRef(id="ws-1", name="   ")


def test_workspace_ref_is_immutable():
    workspace = WorkspaceRef(id="ws-1", name="Workspace 1")
    with pytest.raises(dataclasses.FrozenInstanceError):
        workspace.id = "ws-2"
