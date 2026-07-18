import pytest

from api_quality_agent.adapters.postman import PostmanApiClient
from api_quality_agent.domain.exceptions import (
    AuthenticationError,
    ConflictError,
    IntegrationError,
    ResourceNotFoundError,
)

FAKE_API_KEY = "PMAK-super-secret-key-1234567890abcdef"


def _make_client(server, **overrides) -> PostmanApiClient:
    params = {
        "api_key": FAKE_API_KEY,
        "base_url": server.base_url,
        "timeout_seconds": 2.0,
        "max_retries": 2,
        "retry_backoff_seconds": 0.01,
        "sleep_fn": lambda _seconds: None,
    }
    params.update(overrides)
    return PostmanApiClient(**params)


# --- Autenticação válida --------------------------------------------------------


def test_validate_authentication_succeeds_and_sends_api_key_header(postman_test_server):
    postman_test_server.set_route("/me", status=200, body={"user": {"id": 1, "username": "crys"}})
    client = _make_client(postman_test_server)

    client.validate_authentication()

    assert postman_test_server.received_headers[0]["X-Api-Key"] == FAKE_API_KEY


def test_get_returns_parsed_json_body(postman_test_server):
    postman_test_server.set_route("/workspaces", status=200, body={"workspaces": []})
    client = _make_client(postman_test_server)

    result = client.get("/workspaces")

    assert result == {"workspaces": []}


# --- 401 -------------------------------------------------------------------------


def test_401_raises_authentication_error_without_retry(postman_test_server):
    postman_test_server.set_route("/me", status=401, body={"error": {"message": "invalid key"}})
    client = _make_client(postman_test_server)

    with pytest.raises(AuthenticationError):
        client.validate_authentication()

    assert len(postman_test_server.received_paths) == 1  # nenhum retry para 401


# --- 403 -------------------------------------------------------------------------


def test_403_raises_authentication_error_without_retry(postman_test_server):
    postman_test_server.set_route("/workspaces", status=403, body={"error": {"message": "forbidden"}})
    client = _make_client(postman_test_server)

    with pytest.raises(AuthenticationError):
        client.get("/workspaces")

    assert len(postman_test_server.received_paths) == 1


def test_404_raises_resource_not_found_without_retry(postman_test_server):
    postman_test_server.set_route("/collections/xyz", status=404, body={"error": "not found"})
    client = _make_client(postman_test_server)

    with pytest.raises(ResourceNotFoundError):
        client.get("/collections/xyz")

    assert len(postman_test_server.received_paths) == 1


# --- 429 -------------------------------------------------------------------------


def test_429_retries_and_succeeds_when_a_later_attempt_works(postman_test_server):
    postman_test_server.set_route("/workspaces", status=429, body={"error": "rate limited"})

    def recover_after_first_backoff(_seconds: float) -> None:
        # simula o servidor se recuperando entre a primeira tentativa (429) e
        # o próximo retry, disparado pelo sleep do backoff.
        postman_test_server.set_route("/workspaces", status=200, body={"workspaces": []})

    client = _make_client(postman_test_server, max_retries=3, sleep_fn=recover_after_first_backoff)

    result = client.get("/workspaces")

    assert result == {"workspaces": []}
    assert len(postman_test_server.received_paths) == 2  # 1 falha + 1 sucesso


def test_429_exhausts_retries_and_raises_integration_error(postman_test_server):
    postman_test_server.set_route("/workspaces", status=429, body={"error": "rate limited"})
    client = _make_client(postman_test_server, max_retries=2)

    with pytest.raises(IntegrationError):
        client.get("/workspaces")

    assert len(postman_test_server.received_paths) == 3  # tentativa inicial + 2 retries


# --- Timeout -----------------------------------------------------------------------


def test_timeout_retries_and_then_raises_integration_error(postman_test_server):
    postman_test_server.set_route("/workspaces", status=200, body={"workspaces": []}, delay=0.5)
    client = _make_client(postman_test_server, timeout_seconds=0.05, max_retries=1)

    with pytest.raises(IntegrationError):
        client.get("/workspaces")


# --- Resposta inválida ---------------------------------------------------------------


def test_malformed_json_response_raises_integration_error(postman_test_server):
    postman_test_server.set_raw_route("/workspaces", status=200, raw_body="isto não é json")
    client = _make_client(postman_test_server)

    with pytest.raises(IntegrationError):
        client.get("/workspaces")


def test_unexpected_status_code_raises_integration_error(postman_test_server):
    postman_test_server.set_route("/workspaces", status=418, body={"error": "teapot"})
    client = _make_client(postman_test_server)

    with pytest.raises(IntegrationError):
        client.get("/workspaces")


# --- Mascaramento em logs e exceções --------------------------------------------------


def test_api_key_never_appears_in_authentication_error_message(postman_test_server):
    postman_test_server.set_route("/me", status=401, body={"error": {"message": "invalid"}})
    client = _make_client(postman_test_server)

    with pytest.raises(AuthenticationError) as exc_info:
        client.validate_authentication()

    assert FAKE_API_KEY not in str(exc_info.value)


def test_api_key_never_appears_in_integration_error_message(postman_test_server):
    postman_test_server.set_route("/workspaces", status=500, body={"error": "boom"})
    client = _make_client(postman_test_server, max_retries=0)

    with pytest.raises(IntegrationError) as exc_info:
        client.get("/workspaces")

    assert FAKE_API_KEY not in str(exc_info.value)


def test_api_key_is_only_sent_via_header_never_in_url(postman_test_server):
    postman_test_server.set_route("/workspaces", status=200, body={"workspaces": []})
    client = _make_client(postman_test_server)

    client.get("/workspaces")

    # a chave nunca deve aparecer na query string / path recebido pelo servidor
    assert all(FAKE_API_KEY not in path for path in postman_test_server.received_paths)


def test_constructor_rejects_empty_api_key():
    from api_quality_agent.domain.exceptions import InputError

    with pytest.raises(InputError):
        PostmanApiClient("")


# --- PUT (usado pela atualização remota) ------------------------------------------


def test_put_sends_json_body_with_content_type_and_returns_parsed_response(postman_test_server):
    postman_test_server.set_route(
        "/collections/c1", method="PUT", status=200, body={"collection": {"id": "c1"}}
    )
    client = _make_client(postman_test_server)

    result = client.put("/collections/c1", {"collection": {"info": {"name": "Col"}}})

    assert result == {"collection": {"id": "c1"}}
    assert postman_test_server.received_methods[0] == "PUT"
    assert postman_test_server.received_bodies[0] == {"collection": {"info": {"name": "Col"}}}
    assert postman_test_server.received_headers[0]["Content-Type"] == "application/json"
    assert postman_test_server.received_headers[0]["X-Api-Key"] == FAKE_API_KEY


def test_put_401_raises_authentication_error_without_retry(postman_test_server):
    postman_test_server.set_route(
        "/collections/c1", method="PUT", status=401, body={"error": "invalid key"}
    )
    client = _make_client(postman_test_server)

    with pytest.raises(AuthenticationError):
        client.put("/collections/c1", {"collection": {}})

    assert len(postman_test_server.received_paths) == 1


def test_put_409_raises_conflict_error_without_retry(postman_test_server):
    postman_test_server.set_route(
        "/collections/c1", method="PUT", status=409, body={"error": "conflict"}
    )
    client = _make_client(postman_test_server)

    with pytest.raises(ConflictError):
        client.put("/collections/c1", {"collection": {}})

    assert len(postman_test_server.received_paths) == 1


def test_put_429_retries_and_succeeds_when_a_later_attempt_works(postman_test_server):
    postman_test_server.set_route(
        "/collections/c1", method="PUT", status=429, body={"error": "rate limited"}
    )

    def recover_after_first_backoff(_seconds: float) -> None:
        postman_test_server.set_route(
            "/collections/c1", method="PUT", status=200, body={"collection": {"id": "c1"}}
        )

    client = _make_client(postman_test_server, max_retries=3, sleep_fn=recover_after_first_backoff)

    result = client.put("/collections/c1", {"collection": {}})

    assert result == {"collection": {"id": "c1"}}
    assert len(postman_test_server.received_paths) == 2


def test_put_5xx_exhausts_retries_and_raises_integration_error(postman_test_server):
    postman_test_server.set_route(
        "/collections/c1", method="PUT", status=503, body={"error": "unavailable"}
    )
    client = _make_client(postman_test_server, max_retries=2)

    with pytest.raises(IntegrationError):
        client.put("/collections/c1", {"collection": {}})

    assert len(postman_test_server.received_paths) == 3  # tentativa inicial + 2 retries


def test_put_api_key_never_appears_in_conflict_error_message(postman_test_server):
    postman_test_server.set_route(
        "/collections/c1", method="PUT", status=409, body={"error": "conflict"}
    )
    client = _make_client(postman_test_server)

    with pytest.raises(ConflictError) as exc_info:
        client.put("/collections/c1", {"collection": {}})

    assert FAKE_API_KEY not in str(exc_info.value)
