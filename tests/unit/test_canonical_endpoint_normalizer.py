import pytest

from api_quality_agent.domain.exceptions import InvalidPostmanCollectionError
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
