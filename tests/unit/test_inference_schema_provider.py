import json

from api_quality_agent.domain.models import CollectionExample, CollectionRequest
from api_quality_agent.domain.services import InferenceSchemaProvider, SchemaInferenceEngine


def _request(method, url, examples=()):
    return CollectionRequest(
        item_id=None,
        name="Request",
        description=None,
        method=method,
        url=url,
        url_raw=url if isinstance(url, str) else None,
        headers=(),
        body=None,
        auth=None,
        events=(),
        examples=examples,
    )


def _example(body):
    return CollectionExample(name="ok", status=None, code=200, headers=(), body=body, raw={})


def _provider():
    return InferenceSchemaProvider(SchemaInferenceEngine())


def test_infers_schema_from_valid_json_examples():
    request = _request("GET", "/v2/pet", examples=(_example(json.dumps({"id": 1, "name": "Rex"})),))

    resolution = _provider().resolve(request)

    assert resolution.schema is not None
    assert resolution.schema["type"] == "object"


def test_no_examples_returns_none_schema():
    request = _request("GET", "/v2/pet", examples=())

    resolution = _provider().resolve(request)

    assert resolution.schema is None
    assert resolution.warnings == ()


def test_malformed_json_examples_are_skipped():
    request = _request("GET", "/v2/pet", examples=(_example("not json"),))

    resolution = _provider().resolve(request)

    assert resolution.schema is None


def test_example_without_body_is_skipped():
    request = _request("GET", "/v2/pet", examples=(_example(None),))

    resolution = _provider().resolve(request)

    assert resolution.schema is None


def test_valid_and_invalid_examples_mixed_still_infers_from_the_valid_ones():
    request = _request(
        "GET",
        "/v2/pet",
        examples=(_example("not json"), _example(json.dumps({"id": 1}))),
    )

    resolution = _provider().resolve(request)

    assert resolution.schema is not None
