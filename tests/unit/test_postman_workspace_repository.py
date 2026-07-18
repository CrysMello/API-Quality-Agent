import pytest

from api_quality_agent.adapters.postman import PostmanApiClient, PostmanWorkspaceRepository
from api_quality_agent.domain.exceptions import IntegrationError
from api_quality_agent.domain.models import WorkspaceRef


def _make_repository(server) -> PostmanWorkspaceRepository:
    client = PostmanApiClient(
        "fake-key", base_url=server.base_url, timeout_seconds=2.0, max_retries=0
    )
    return PostmanWorkspaceRepository(client)


def test_list_translates_response_into_workspace_refs(postman_test_server):
    postman_test_server.set_route(
        "/workspaces",
        status=200,
        body={
            "workspaces": [
                {"id": "ws-1", "name": "Workspace 1", "type": "personal"},
                {"id": "ws-2", "name": "Workspace 2", "type": "team"},
            ]
        },
    )
    repository = _make_repository(postman_test_server)

    workspaces = repository.list()

    assert workspaces == (
        WorkspaceRef(id="ws-1", name="Workspace 1"),
        WorkspaceRef(id="ws-2", name="Workspace 2"),
    )


def test_list_skips_malformed_entries(postman_test_server):
    postman_test_server.set_route(
        "/workspaces",
        status=200,
        body={
            "workspaces": [
                {"id": "ws-1", "name": "Workspace válido"},
                {"id": "ws-2"},  # sem "name": descartado
                {"name": "Sem id"},  # sem "id": descartado
                "não é um objeto",
            ]
        },
    )
    repository = _make_repository(postman_test_server)

    workspaces = repository.list()

    assert workspaces == (WorkspaceRef(id="ws-1", name="Workspace válido"),)


def test_list_raises_for_missing_workspaces_key(postman_test_server):
    postman_test_server.set_route("/workspaces", status=200, body={"unexpected": True})
    repository = _make_repository(postman_test_server)

    with pytest.raises(IntegrationError):
        repository.list()


def test_list_raises_for_non_list_workspaces_value(postman_test_server):
    postman_test_server.set_route("/workspaces", status=200, body={"workspaces": "not-a-list"})
    repository = _make_repository(postman_test_server)

    with pytest.raises(IntegrationError):
        repository.list()
