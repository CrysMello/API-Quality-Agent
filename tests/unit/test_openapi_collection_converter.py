import json

from api_quality_agent.domain.models import (
    ApiSpecification,
    ApiSpecificationType,
    CollectionRequest,
    Endpoint,
    MediaTypeDefinition,
    Parameter,
    ParameterLocation,
    RequestDefinition,
    ResponseDefinition,
)
from api_quality_agent.parsers.openapi_collection_converter import OpenApiCollectionConverter


def _specification(*, endpoints, servers=("https://api.exemplo.com/v1",), title="Minha API"):
    return ApiSpecification(
        spec_type=ApiSpecificationType.OPENAPI,
        spec_version="3.0.0",
        title=title,
        api_version="1.0",
        servers=servers,
        endpoints=tuple(endpoints),
        security_schemes=(),
    )


def _endpoint(**overrides):
    defaults = dict(
        method="GET",
        path="/pets",
        operation_id="listPets",
        summary="Lista pets",
        parameters=(),
        request=None,
        responses=(),
        security_requirement_names=(),
    )
    defaults.update(overrides)
    return Endpoint(**defaults)


def _converted_request(specification) -> CollectionRequest:
    document = OpenApiCollectionConverter().convert(specification)
    assert len(document.items) == 1
    request = document.items[0]
    assert isinstance(request, CollectionRequest)
    return request


def test_endpoint_with_response_example_becomes_a_collection_example():
    endpoint = _endpoint(
        responses=(
            ResponseDefinition(
                status_code="200",
                description="OK",
                media_types=(
                    MediaTypeDefinition(
                        content_type="application/json",
                        schema={"type": "object"},
                        example={"id": 1, "name": "Rex"},
                    ),
                ),
            ),
        ),
    )

    request = _converted_request(_specification(endpoints=[endpoint]))

    assert len(request.examples) == 1
    example = request.examples[0]
    assert example.code == 200
    assert json.loads(example.body) == {"id": 1, "name": "Rex"}
    assert example.raw["code"] == 200


def test_endpoint_with_request_example_becomes_raw_json_body():
    endpoint = _endpoint(
        method="POST",
        path="/pets",
        request=RequestDefinition(
            required=True,
            description=None,
            media_types=(
                MediaTypeDefinition(
                    content_type="application/json",
                    schema={"type": "object"},
                    example={"name": "Rex"},
                ),
            ),
        ),
    )

    request = _converted_request(_specification(endpoints=[endpoint]))

    assert request.body is not None
    assert request.body["mode"] == "raw"
    assert json.loads(request.body["raw"]) == {"name": "Rex"}


def test_endpoint_without_examples_never_invents_body_or_examples():
    endpoint = _endpoint(
        request=RequestDefinition(
            required=True,
            description=None,
            media_types=(
                MediaTypeDefinition(content_type="application/json", schema={"type": "object"}, example=None),
            ),
        ),
        responses=(
            ResponseDefinition(
                status_code="200",
                description="OK",
                media_types=(
                    MediaTypeDefinition(content_type="application/json", schema={"type": "object"}, example=None),
                ),
            ),
        ),
    )

    request = _converted_request(_specification(endpoints=[endpoint]))

    assert request.body is None
    assert request.examples == ()


def test_path_parameter_is_converted_to_postman_variable_style():
    endpoint = _endpoint(
        path="/pets/{petId}",
        parameters=(
            Parameter(
                name="petId",
                location=ParameterLocation.PATH,
                required=True,
                schema={"type": "string"},
                example="abc-123",
            ),
        ),
    )

    request = _converted_request(_specification(endpoints=[endpoint]))

    assert request.url["path"][-1] == ":petId"
    assert {"key": "petId", "value": "abc-123"} in request.url["variable"]


def test_query_and_header_parameters_are_mapped():
    endpoint = _endpoint(
        parameters=(
            Parameter(
                name="limit", location=ParameterLocation.QUERY, required=False, schema=None, example=10
            ),
            Parameter(
                name="X-Trace-Id", location=ParameterLocation.HEADER, required=False, schema=None, example="abc"
            ),
        ),
    )

    request = _converted_request(_specification(endpoints=[endpoint]))

    assert request.url["query"] == [{"key": "limit", "value": "10", "disabled": False}]
    assert request.headers == ({"key": "X-Trace-Id", "value": "abc", "disabled": False},)


def test_missing_server_produces_a_warning_not_an_error():
    document = OpenApiCollectionConverter().convert(
        _specification(endpoints=[_endpoint()], servers=())
    )

    assert document.warnings
    assert document.items[0].url["protocol"] is None


def test_events_start_empty_so_the_orchestrator_can_inject_the_generated_script():
    request = _converted_request(_specification(endpoints=[_endpoint()]))

    assert request.events == ()
