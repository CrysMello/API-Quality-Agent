import pytest

from api_quality_agent.domain.exceptions import InputError, InvalidPostmanCollectionError
from api_quality_agent.domain.services import CanonicalEndpointNormalizer

_EQUIVALENT_URLS = [
    "/users/{id}",
    "/users/:id",
    "/users/{{id}}",
    "https://api.company.com/users/{{id}}",
    "https://api.company.com/users/{id}?expand=true",
]


@pytest.mark.parametrize("raw_url", _EQUIVALENT_URLS)
def test_equivalent_string_urls_produce_the_same_canonical_path(raw_url):
    endpoint = CanonicalEndpointNormalizer().normalize_collection_request("get", raw_url)

    assert endpoint.canonical_path == "/users/{param}"
    assert endpoint.method == "GET"


def test_prefers_url_path_over_raw():
    url = {
        "raw": "{{baseUrl}}/v2/pet/{{petId}}",
        "host": ["{{baseUrl}}"],
        "path": ["v2", "pet", "{{petId}}"],
    }

    endpoint = CanonicalEndpointNormalizer().normalize_collection_request("GET", url)

    assert endpoint.canonical_path == "/v2/pet/{param}"


def test_falls_back_to_raw_when_path_is_absent():
    url = {"raw": "{{baseUrl}}/v2/pet"}

    endpoint = CanonicalEndpointNormalizer().normalize_collection_request("POST", url)

    assert endpoint.canonical_path == "/v2/pet"


def test_falls_back_to_raw_when_path_is_empty_list():
    url = {"raw": "https://api.company.com/v2/pet", "path": []}

    endpoint = CanonicalEndpointNormalizer().normalize_collection_request("POST", url)

    assert endpoint.canonical_path == "/v2/pet"


def test_infrastructure_variable_in_host_never_pollutes_the_path():
    url = {
        "raw": "{{baseUrl}}/v2/pet/findByStatus?status=available",
        "host": ["{{baseUrl}}"],
        "path": ["v2", "pet", "findByStatus"],
        "query": [{"key": "status", "value": "available"}],
    }

    endpoint = CanonicalEndpointNormalizer().normalize_collection_request("GET", url)

    assert endpoint.canonical_path == "/v2/pet/findByStatus"


def test_missing_path_and_raw_raises_invalid_collection_error():
    with pytest.raises(InvalidPostmanCollectionError):
        CanonicalEndpointNormalizer().normalize_collection_request("GET", {})


def test_none_url_raises_invalid_collection_error():
    with pytest.raises(InvalidPostmanCollectionError):
        CanonicalEndpointNormalizer().normalize_collection_request("GET", None)


def test_missing_method_raises_invalid_collection_error():
    with pytest.raises(InvalidPostmanCollectionError):
        CanonicalEndpointNormalizer().normalize_collection_request(None, "/users/{id}")


def test_declared_endpoint_path_is_normalized_the_same_way():
    endpoint = CanonicalEndpointNormalizer().normalize_declared_endpoint(
        "post", "/teste/cotacao/{origem}"
    )

    assert endpoint.method == "POST"
    assert endpoint.canonical_path == "/teste/cotacao/{param}"


def test_partial_segment_placeholder_is_not_treated_as_a_full_parameter():
    # "v{version}" mistura texto literal ("v") com um placeholder — só um
    # segmento inteiramente entre chaves/dois-pontos vira "{param}".
    endpoint = CanonicalEndpointNormalizer().normalize_declared_endpoint(
        "GET", "/teste/v{version}/cotacao/{origem}"
    )

    assert endpoint.canonical_path == "/teste/v{version}/cotacao/{param}"


def test_duplicate_and_trailing_slashes_are_normalized():
    endpoint = CanonicalEndpointNormalizer().normalize_collection_request("GET", "/v2//pet/")

    assert endpoint.canonical_path == "/v2/pet"


# --collection-path-prefix: prefixo fixo de path (ex.: gateway) presente só
# nas requests da Collection, ausente do path declarado no contrato.


def test_collection_path_prefix_is_removed_via_url_path_list():
    url = {"path": ["api", "v1", "users", "{{id}}"]}

    endpoint = CanonicalEndpointNormalizer(collection_path_prefix="/api").normalize_collection_request(
        "GET", url
    )

    assert endpoint.canonical_path == "/v1/users/{param}"


def test_collection_path_prefix_is_removed_via_url_raw_string():
    endpoint = CanonicalEndpointNormalizer(
        collection_path_prefix="/api"
    ).normalize_collection_request("GET", "https://api.company.com/api/v1/users/{{id}}")

    assert endpoint.canonical_path == "/v1/users/{param}"


def test_collection_path_prefix_absent_from_path_leaves_it_unchanged():
    endpoint = CanonicalEndpointNormalizer(
        collection_path_prefix="/api"
    ).normalize_collection_request("GET", "/v1/users/{{id}}")

    assert endpoint.canonical_path == "/v1/users/{param}"


@pytest.mark.parametrize(
    "raw_url",
    [
        "/v10/users",
        "/v1beta/users",
        "/service/v1/users",
    ],
)
def test_collection_path_prefix_never_matches_partial_or_internal_segments(raw_url):
    endpoint = CanonicalEndpointNormalizer(collection_path_prefix="/v1").normalize_collection_request(
        "GET", raw_url
    )

    assert endpoint.canonical_path == raw_url


def test_declared_endpoint_never_receives_the_collection_path_prefix():
    endpoint = CanonicalEndpointNormalizer(collection_path_prefix="/api").normalize_declared_endpoint(
        "GET", "/api/v1/users/{id}"
    )

    # normalize_declared_endpoint nunca remove prefixo: o path declarado no
    # contrato já é a fonte de verdade, sem o prefixo da Collection.
    assert endpoint.canonical_path == "/api/v1/users/{param}"


@pytest.mark.parametrize("prefix_value", ["/api", "api", "/api/", "api/"])
def test_collection_path_prefix_value_ignores_surrounding_slashes(prefix_value):
    endpoint = CanonicalEndpointNormalizer(
        collection_path_prefix=prefix_value
    ).normalize_collection_request("GET", "/api/v1/users")

    assert endpoint.canonical_path == "/v1/users"


def test_multi_segment_collection_path_prefix_is_supported():
    endpoint = CanonicalEndpointNormalizer(
        collection_path_prefix="/api/v1"
    ).normalize_collection_request("GET", "/api/v1/users/{{id}}")

    assert endpoint.canonical_path == "/users/{param}"


def test_absent_collection_path_prefix_keeps_current_behavior():
    endpoint = CanonicalEndpointNormalizer(collection_path_prefix=None).normalize_collection_request(
        "GET", "/api/v1/users/{{id}}"
    )

    assert endpoint.canonical_path == "/api/v1/users/{param}"


@pytest.mark.parametrize("invalid_prefix", ["", "   ", "////"])
def test_collection_path_prefix_with_no_usable_segment_raises_input_error(invalid_prefix):
    with pytest.raises(InputError):
        CanonicalEndpointNormalizer(collection_path_prefix=invalid_prefix)
