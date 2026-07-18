import pytest

from api_quality_agent.adapters.postman import PostmanApiClient, PostmanCollectionRepository
from api_quality_agent.domain.exceptions import IntegrationError
from api_quality_agent.domain.models import CollectionRef, PostmanCollectionDocument


def _make_repository(server) -> PostmanCollectionRepository:
    client = PostmanApiClient(
        "fake-key", base_url=server.base_url, timeout_seconds=2.0, max_retries=0
    )
    return PostmanCollectionRepository(client)


# --- Lista de Collections -----------------------------------------------------------


def test_list_translates_response_into_collection_refs(postman_test_server):
    postman_test_server.set_route(
        "/collections?workspace=ws-1",
        status=200,
        body={
            "collections": [
                {"id": "c1", "uid": "123-c1", "name": "Collection A"},
                {"id": "c2", "uid": "123-c2", "name": "Collection B"},
            ]
        },
    )
    repository = _make_repository(postman_test_server)

    collections = repository.list("ws-1")

    assert collections == (
        CollectionRef(id="123-c1", name="Collection A", workspace_id="ws-1"),
        CollectionRef(id="123-c2", name="Collection B", workspace_id="ws-1"),
    )


def test_list_falls_back_to_id_when_uid_is_absent(postman_test_server):
    postman_test_server.set_route(
        "/collections?workspace=ws-1",
        status=200,
        body={"collections": [{"id": "c1", "name": "Collection A"}]},
    )
    repository = _make_repository(postman_test_server)

    collections = repository.list("ws-1")

    assert collections == (CollectionRef(id="c1", name="Collection A", workspace_id="ws-1"),)


def test_list_raises_for_invalid_response_shape(postman_test_server):
    postman_test_server.set_route("/collections?workspace=ws-1", status=200, body={"oops": True})
    repository = _make_repository(postman_test_server)

    with pytest.raises(IntegrationError):
        repository.list("ws-1")


# --- Obter Collection ------------------------------------------------------------------


def test_get_translates_response_into_postman_collection_document(postman_test_server):
    postman_test_server.set_route(
        "/collections/123-c1",
        status=200,
        body={
            "collection": {
                "info": {
                    "name": "Minha Collection",
                    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
                },
                "item": [
                    {"name": "Ping", "request": {"method": "GET", "url": "https://x/y"}}
                ],
            }
        },
    )
    repository = _make_repository(postman_test_server)

    document = repository.get("123-c1")

    assert isinstance(document, PostmanCollectionDocument)
    assert document.name == "Minha Collection"
    assert len(document.items) == 1


def test_get_raises_for_invalid_response_shape(postman_test_server):
    postman_test_server.set_route("/collections/123-c1", status=200, body={"oops": True})
    repository = _make_repository(postman_test_server)

    with pytest.raises(IntegrationError):
        repository.get("123-c1")
