import json

import pytest

from api_quality_agent.domain.exceptions import (
    InvalidApiSpecificationError,
    UnsupportedSpecificationVersionError,
)
from api_quality_agent.domain.models import ApiSpecificationType, InputOrigin, ParameterLocation, ResolvedInput
from api_quality_agent.parsers import OpenApiParser


def test_parses_minimal_openapi3_document():
    text = json.dumps(
        {
            "openapi": "3.0.3",
            "info": {"title": "Minimal API", "version": "1.0.0"},
            "paths": {
                "/health": {
                    "get": {
                        "operationId": "getHealth",
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
        }
    )

    spec = OpenApiParser().parse_text(text, source_name="minimal.json")

    assert spec.spec_type == ApiSpecificationType.OPENAPI
    assert spec.spec_version == "3.0.3"
    assert spec.title == "Minimal API"
    assert spec.api_version == "1.0.0"
    assert len(spec.endpoints) == 1
    endpoint = spec.endpoints[0]
    assert endpoint.method == "GET"
    assert endpoint.path == "/health"
    assert endpoint.operation_id == "getHealth"
    assert endpoint.responses[0].status_code == "200"
    assert endpoint.responses[0].description == "OK"


def test_parses_openapi3_with_components_and_ref():
    text = json.dumps(
        {
            "openapi": "3.0.3",
            "info": {"title": "API", "version": "1.0.0"},
            "paths": {
                "/pets": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "Lista de pets",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "array",
                                            "items": {"$ref": "#/components/schemas/Pet"},
                                        }
                                    }
                                },
                            }
                        }
                    }
                }
            },
            "components": {
                "schemas": {
                    "Pet": {
                        "type": "object",
                        "required": ["id", "name"],
                        "properties": {
                            "id": {"type": "integer"},
                            "name": {"type": "string"},
                        },
                    }
                }
            },
        }
    )

    spec = OpenApiParser().parse_text(text)

    schema = spec.endpoints[0].responses[0].media_types[0].schema
    assert schema["items"] == {
        "type": "object",
        "required": ["id", "name"],
        "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
    }


def test_parses_minimal_swagger2_document():
    text = json.dumps(
        {
            "swagger": "2.0",
            "info": {"title": "Legacy API", "version": "1.0.0"},
            "host": "api.exemplo.com",
            "basePath": "/v1",
            "schemes": ["https"],
            "paths": {
                "/status": {
                    "get": {
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
        }
    )

    spec = OpenApiParser().parse_text(text)

    assert spec.spec_type == ApiSpecificationType.SWAGGER
    assert spec.spec_version == "2.0"
    assert spec.servers == ("https://api.exemplo.com/v1",)
    assert len(spec.endpoints) == 1


def test_json_and_yaml_produce_equivalent_specifications():
    json_text = json.dumps(
        {
            "openapi": "3.0.3",
            "info": {"title": "API", "version": "1.0.0"},
            "paths": {"/ping": {"get": {"responses": {"200": {"description": "pong"}}}}},
        }
    )
    yaml_text = """
openapi: "3.0.3"
info:
  title: API
  version: "1.0.0"
paths:
  /ping:
    get:
      responses:
        "200":
          description: pong
"""
    parser = OpenApiParser()
    spec_from_json = parser.parse_text(json_text, source_name="doc.json")
    spec_from_yaml = parser.parse_text(yaml_text, source_name="doc.yaml")

    assert spec_from_json.title == spec_from_yaml.title
    assert spec_from_json.endpoints[0].path == spec_from_yaml.endpoints[0].path
    assert (
        spec_from_json.endpoints[0].responses[0].description
        == spec_from_yaml.endpoints[0].responses[0].description
    )


def test_extracts_openapi3_request_body():
    text = json.dumps(
        {
            "openapi": "3.0.3",
            "info": {"title": "API", "version": "1.0.0"},
            "paths": {
                "/pets": {
                    "post": {
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["name"],
                                        "properties": {"name": {"type": "string"}},
                                    },
                                    "example": {"name": "Rex"},
                                }
                            },
                        },
                        "responses": {"201": {"description": "Criado"}},
                    }
                }
            },
        }
    )

    spec = OpenApiParser().parse_text(text)
    request = spec.endpoints[0].request

    assert request is not None
    assert request.required is True
    assert request.media_types[0].content_type == "application/json"
    assert request.media_types[0].schema["required"] == ["name"]
    assert request.media_types[0].example == {"name": "Rex"}


def test_extracts_swagger2_body_parameter_as_request_definition():
    text = json.dumps(
        {
            "swagger": "2.0",
            "info": {"title": "API", "version": "1.0.0"},
            "paths": {
                "/pets": {
                    "post": {
                        "consumes": ["application/json"],
                        "parameters": [
                            {
                                "name": "body",
                                "in": "body",
                                "required": True,
                                "schema": {
                                    "type": "object",
                                    "required": ["name"],
                                    "properties": {"name": {"type": "string"}},
                                },
                            }
                        ],
                        "responses": {"201": {"description": "Criado"}},
                    }
                }
            },
        }
    )

    spec = OpenApiParser().parse_text(text)
    request = spec.endpoints[0].request

    assert request is not None
    assert request.required is True
    assert request.media_types[0].content_type == "application/json"
    assert request.media_types[0].schema["required"] == ["name"]
    assert spec.endpoints[0].parameters == ()


def test_extracts_multiple_responses():
    text = json.dumps(
        {
            "openapi": "3.0.3",
            "info": {"title": "API", "version": "1.0.0"},
            "paths": {
                "/pets/{id}": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "OK",
                                "content": {"application/json": {"schema": {"type": "object"}}},
                            },
                            "404": {"description": "Não encontrado"},
                            "default": {"description": "Erro inesperado"},
                        }
                    }
                }
            },
        }
    )

    spec = OpenApiParser().parse_text(text)
    status_codes = {response.status_code for response in spec.endpoints[0].responses}

    assert status_codes == {"200", "404", "default"}


def test_extracts_openapi3_security_schemes_and_endpoint_requirements():
    text = json.dumps(
        {
            "openapi": "3.0.3",
            "info": {"title": "API", "version": "1.0.0"},
            "paths": {
                "/secure": {
                    "get": {
                        "security": [{"apiKeyAuth": []}],
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
            "components": {
                "securitySchemes": {
                    "apiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
                    "bearerAuth": {"type": "http", "scheme": "bearer"},
                }
            },
        }
    )

    spec = OpenApiParser().parse_text(text)

    names = {scheme.name for scheme in spec.security_schemes}
    assert names == {"apiKeyAuth", "bearerAuth"}

    api_key_scheme = next(s for s in spec.security_schemes if s.name == "apiKeyAuth")
    assert api_key_scheme.type == "apiKey"
    assert api_key_scheme.location == "header"
    assert api_key_scheme.parameter_name == "X-API-Key"

    assert spec.endpoints[0].security_requirement_names == ("apiKeyAuth",)


def test_extracts_swagger2_security_definitions():
    text = json.dumps(
        {
            "swagger": "2.0",
            "info": {"title": "API", "version": "1.0.0"},
            "paths": {"/status": {"get": {"responses": {"200": {"description": "OK"}}}}},
            "securityDefinitions": {"basicAuth": {"type": "basic"}},
        }
    )

    spec = OpenApiParser().parse_text(text)

    assert len(spec.security_schemes) == 1
    assert spec.security_schemes[0].name == "basicAuth"
    assert spec.security_schemes[0].type == "basic"


def test_parser_handles_circular_reference_without_crashing():
    text = json.dumps(
        {
            "openapi": "3.0.3",
            "info": {"title": "API", "version": "1.0.0"},
            "paths": {
                "/nodes": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "OK",
                                "content": {
                                    "application/json": {"schema": {"$ref": "#/components/schemas/Node"}}
                                },
                            }
                        }
                    }
                }
            },
            "components": {
                "schemas": {
                    "Node": {
                        "type": "object",
                        "properties": {
                            "children": {
                                "type": "array",
                                "items": {"$ref": "#/components/schemas/Node"},
                            }
                        },
                    }
                }
            },
        }
    )

    spec = OpenApiParser().parse_text(text)

    schema = spec.endpoints[0].responses[0].media_types[0].schema
    assert schema["properties"]["children"]["items"] == {"$ref": "#/components/schemas/Node"}


def test_parser_registers_warning_for_external_reference():
    text = json.dumps(
        {
            "openapi": "3.0.3",
            "info": {"title": "API", "version": "1.0.0"},
            "paths": {
                "/pets": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "OK",
                                "content": {
                                    "application/json": {"schema": {"$ref": "common.yaml#/Pet"}}
                                },
                            }
                        }
                    }
                }
            },
        }
    )

    spec = OpenApiParser().parse_text(text)

    assert len(spec.warnings) == 1
    assert "common.yaml#/Pet" in spec.warnings[0]
    schema = spec.endpoints[0].responses[0].media_types[0].schema
    assert schema == {"$ref": "common.yaml#/Pet"}


def test_raises_for_document_without_openapi_or_swagger_key():
    text = json.dumps({"info": {"title": "API"}, "paths": {}})

    with pytest.raises(InvalidApiSpecificationError):
        OpenApiParser().parse_text(text)


def test_raises_for_malformed_content():
    with pytest.raises(InvalidApiSpecificationError):
        OpenApiParser().parse_text("{ isto nao e nem json nem yaml valido: : :")


def test_raises_for_non_object_root():
    text = json.dumps([1, 2, 3])

    with pytest.raises(InvalidApiSpecificationError):
        OpenApiParser().parse_text(text)


def test_raises_for_unsupported_openapi_version():
    text = json.dumps({"openapi": "2.5.0", "info": {"title": "x", "version": "1.0"}, "paths": {}})

    with pytest.raises(UnsupportedSpecificationVersionError):
        OpenApiParser().parse_text(text)


def test_raises_for_unsupported_swagger_version():
    text = json.dumps({"swagger": "1.2", "info": {"title": "x", "version": "1.0"}, "paths": {}})

    with pytest.raises(UnsupportedSpecificationVersionError):
        OpenApiParser().parse_text(text)


def test_ignores_non_method_keys_and_merges_path_level_parameters():
    text = json.dumps(
        {
            "openapi": "3.0.3",
            "info": {"title": "API", "version": "1.0.0"},
            "paths": {
                "/pets": {
                    "parameters": [
                        {"name": "shared", "in": "query", "schema": {"type": "string"}}
                    ],
                    "summary": "Operações de pets",
                    "get": {"responses": {"200": {"description": "OK"}}},
                }
            },
        }
    )

    spec = OpenApiParser().parse_text(text)

    assert len(spec.endpoints) == 1
    assert spec.endpoints[0].method == "GET"
    assert spec.endpoints[0].parameters[0].name == "shared"


def test_preserves_required_fields_declared_in_schema():
    text = json.dumps(
        {
            "openapi": "3.0.3",
            "info": {"title": "API", "version": "1.0.0"},
            "paths": {
                "/pets": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["name", "age"],
                                        "properties": {
                                            "name": {"type": "string"},
                                            "age": {"type": "integer"},
                                        },
                                    }
                                }
                            }
                        },
                        "responses": {"201": {"description": "Criado"}},
                    }
                }
            },
        }
    )

    spec = OpenApiParser().parse_text(text)

    schema = spec.endpoints[0].request.media_types[0].schema
    assert schema["required"] == ["name", "age"]


def test_extracts_path_query_header_and_cookie_parameters():
    text = json.dumps(
        {
            "openapi": "3.0.3",
            "info": {"title": "API", "version": "1.0.0"},
            "paths": {
                "/pets/{petId}": {
                    "get": {
                        "parameters": [
                            {
                                "name": "petId",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string"},
                            },
                            {
                                "name": "limit",
                                "in": "query",
                                "required": False,
                                "schema": {"type": "integer"},
                            },
                            {
                                "name": "X-Request-Id",
                                "in": "header",
                                "required": False,
                                "schema": {"type": "string"},
                            },
                            {
                                "name": "session",
                                "in": "cookie",
                                "required": False,
                                "schema": {"type": "string"},
                            },
                        ],
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
        }
    )

    spec = OpenApiParser().parse_text(text)
    locations = {parameter.location for parameter in spec.endpoints[0].parameters}

    assert locations == {
        ParameterLocation.PATH,
        ParameterLocation.QUERY,
        ParameterLocation.HEADER,
        ParameterLocation.COOKIE,
    }
    path_parameter = next(p for p in spec.endpoints[0].parameters if p.location == ParameterLocation.PATH)
    assert path_parameter.required is True


def test_preserves_enum_declared_in_parameter_schema():
    text = json.dumps(
        {
            "openapi": "3.0.3",
            "info": {"title": "API", "version": "1.0.0"},
            "paths": {
                "/pets": {
                    "get": {
                        "parameters": [
                            {
                                "name": "status",
                                "in": "query",
                                "schema": {"type": "string", "enum": ["available", "pending", "sold"]},
                            }
                        ],
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
        }
    )

    spec = OpenApiParser().parse_text(text)

    parameter = spec.endpoints[0].parameters[0]
    assert parameter.schema["enum"] == ["available", "pending", "sold"]


def test_parse_accepts_resolved_input():
    resolved = ResolvedInput(
        origin=InputOrigin.INLINE,
        content_type="yaml",
        name="contract.yaml",
        content="openapi: '3.0.3'\ninfo:\n  title: API\n  version: '1.0.0'\npaths: {}\n",
    )

    spec = OpenApiParser().parse(resolved)

    assert spec.title == "API"
    assert spec.endpoints == ()
