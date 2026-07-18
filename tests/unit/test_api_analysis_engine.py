import json

import pytest

from api_quality_agent.domain.models import DependencyConfidence, DependencyEvidenceType
from api_quality_agent.domain.services import ApiAnalysisEngine
from api_quality_agent.parsers import OpenApiParser, PostmanCollectionParser


def _parse_openapi(paths: dict) -> object:
    document = {
        "openapi": "3.0.3",
        "info": {"title": "API", "version": "1.0.0"},
        "paths": paths,
    }
    return OpenApiParser().parse_text(json.dumps(document))


def _parse_collection(items: list) -> object:
    document = {
        "info": {
            "name": "Collection",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": items,
    }
    return PostmanCollectionParser().parse_text(json.dumps(document))


# --- Endpoints independentes -------------------------------------------------


def test_independent_endpoints_have_no_dependencies():
    spec = _parse_openapi(
        {
            "/users": {"get": {"responses": {"200": {"description": "OK"}}}},
            "/orders": {"get": {"responses": {"200": {"description": "OK"}}}},
        }
    )

    result = ApiAnalysisEngine().analyze(spec)

    assert len(result.endpoints) == 2
    assert result.dependencies == ()


# --- Dependência por variável (Postman) --------------------------------------


def test_dependency_by_variable_is_confirmed():
    document = _parse_collection(
        [
            {
                "name": "Criar pet",
                "request": {"method": "POST", "url": "https://api.exemplo.com/pets"},
                "event": [
                    {
                        "listen": "test",
                        "script": {
                            "exec": [
                                "const data = pm.response.json();",
                                'pm.collectionVariables.set("petId", data.id);',
                            ]
                        },
                    }
                ],
            },
            {
                "name": "Deletar pet",
                "request": {"method": "DELETE", "url": "https://api.exemplo.com/pets/{{petId}}/cancel"},
            },
        ]
    )

    result = ApiAnalysisEngine().analyze(document)

    variable_dependencies = [
        d for d in result.dependencies if d.evidence_type == DependencyEvidenceType.VARIABLE_REFERENCE
    ]
    assert len(variable_dependencies) == 1
    dependency = variable_dependencies[0]
    assert dependency.confidence == DependencyConfidence.CONFIRMED
    assert "Criar pet" in dependency.source_endpoint or "POST" in dependency.source_endpoint
    assert "petId" in dependency.description


def test_variable_used_without_any_definer_generates_no_dependency():
    document = _parse_collection(
        [
            {
                "name": "Usa variável não definida",
                "request": {"method": "GET", "url": "https://api.exemplo.com/pets/{{unknownVar}}"},
            }
        ]
    )

    result = ApiAnalysisEngine().analyze(document)

    assert result.dependencies == ()


# --- Dependência por path (OpenAPI) ------------------------------------------


def test_dependency_by_path_is_confirmed_when_source_creates_resource():
    spec = _parse_openapi(
        {
            "/pets": {
                "post": {
                    "responses": {"201": {"description": "Criado"}},
                }
            },
            "/pets/{id}": {
                "get": {
                    "parameters": [
                        {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            },
        }
    )

    result = ApiAnalysisEngine().analyze(spec)

    path_dependencies = [
        d for d in result.dependencies if d.evidence_type == DependencyEvidenceType.PATH_CORRESPONDENCE
    ]
    assert len(path_dependencies) == 1
    dependency = path_dependencies[0]
    assert dependency.source_endpoint == "POST /pets"
    assert dependency.target_endpoint == "GET /pets/{id}"
    assert dependency.confidence == DependencyConfidence.CONFIRMED


def test_dependency_by_path_is_only_suggested_without_creation_method():
    spec = _parse_openapi(
        {
            "/pets": {"get": {"responses": {"200": {"description": "OK"}}}},
            "/pets/{id}": {
                "get": {
                    "parameters": [
                        {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            },
        }
    )

    result = ApiAnalysisEngine().analyze(spec)

    path_dependencies = [
        d for d in result.dependencies if d.evidence_type == DependencyEvidenceType.PATH_CORRESPONDENCE
    ]
    assert len(path_dependencies) == 1
    assert path_dependencies[0].confidence == DependencyConfidence.SUGGESTED


# --- Campo id sem evidência ---------------------------------------------------


def test_shared_id_field_without_evidence_generates_no_dependency():
    spec = _parse_openapi(
        {
            "/users/{id}": {
                "get": {
                    "parameters": [
                        {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {"id": {"type": "string"}},
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/orders/{id}": {
                "get": {
                    "parameters": [
                        {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {"id": {"type": "string"}},
                                    }
                                }
                            },
                        }
                    },
                }
            },
        }
    )

    result = ApiAnalysisEngine().analyze(spec)

    assert result.dependencies == ()


def test_shared_id_field_in_postman_headers_generates_no_dependency():
    document = _parse_collection(
        [
            {
                "name": "R1",
                "request": {
                    "method": "GET",
                    "url": "https://api.exemplo.com/users/1",
                    "header": [{"key": "X-Id", "value": "1"}],
                },
            },
            {
                "name": "R2",
                "request": {
                    "method": "GET",
                    "url": "https://api.exemplo.com/orders/1",
                    "header": [{"key": "X-Id", "value": "1"}],
                },
            },
        ]
    )

    result = ApiAnalysisEngine().analyze(document)

    assert result.dependencies == ()


# --- Contrato incompleto ------------------------------------------------------


def test_incomplete_contract_generates_warnings():
    spec = _parse_openapi(
        {
            "/pets": {
                "post": {
                    "requestBody": {"content": {}},
                    "parameters": [{"name": "trace", "in": "header", "required": False}],
                    "responses": {},
                }
            }
        }
    )

    result = ApiAnalysisEngine().analyze(spec)

    warning_codes = {w.code for w in result.warnings}
    assert "NO_RESPONSES_DOCUMENTED" in warning_codes
    assert "MISSING_REQUEST_SCHEMA" in warning_codes
    assert "MISSING_PARAMETER_SCHEMA" in warning_codes


# --- Diferentes status codes ---------------------------------------------------


def test_different_status_codes_are_all_reported():
    spec = _parse_openapi(
        {
            "/pets/{id}": {
                "get": {
                    "parameters": [
                        {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
                    "responses": {
                        "200": {"description": "OK"},
                        "404": {"description": "Não encontrado"},
                        "500": {"description": "Erro interno"},
                    },
                }
            }
        }
    )

    result = ApiAnalysisEngine().analyze(spec)

    assert set(result.endpoints[0].response_status_codes) == {"200", "404", "500"}


# --- Ausência de example -------------------------------------------------------


def test_missing_example_generates_warning():
    spec = _parse_openapi(
        {"/pets": {"get": {"responses": {"200": {"description": "OK"}}}}}
    )

    result = ApiAnalysisEngine().analyze(spec)

    assert result.endpoints[0].has_examples is False
    assert result.endpoints[0].example_count == 0
    assert any(w.code == "NO_EXAMPLES_AVAILABLE" for w in result.warnings)


def test_example_present_avoids_missing_example_warning():
    spec = _parse_openapi(
        {
            "/pets": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "array"},
                                    "example": [{"id": 1}],
                                }
                            },
                        }
                    }
                }
            }
        }
    )

    result = ApiAnalysisEngine().analyze(spec)

    assert result.endpoints[0].has_examples is True
    assert result.endpoints[0].example_count == 1
    assert not any(w.code == "NO_EXAMPLES_AVAILABLE" for w in result.warnings)


# --- Resultado determinístico --------------------------------------------------


def test_result_is_deterministic():
    spec = _parse_openapi(
        {
            "/pets": {
                "post": {"responses": {"201": {"description": "Criado"}}},
            },
            "/pets/{id}": {
                "get": {
                    "parameters": [
                        {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            },
        }
    )
    engine = ApiAnalysisEngine()

    first = engine.analyze(spec)
    second = engine.analyze(spec)

    assert first == second


def test_postman_result_is_deterministic():
    document = _parse_collection(
        [
            {
                "name": "R1",
                "request": {"method": "GET", "url": "https://x/y"},
                "event": [
                    {
                        "listen": "test",
                        "script": {"exec": ['pm.environment.set("token", "abc");']},
                    }
                ],
            },
            {"name": "R2", "request": {"method": "GET", "url": "https://x/{{token}}"}},
        ]
    )
    engine = ApiAnalysisEngine()

    first = engine.analyze(document)
    second = engine.analyze(document)

    assert first == second


# --- Comportamento geral -------------------------------------------------------


def test_analyze_raises_type_error_for_unsupported_source():
    with pytest.raises(TypeError):
        ApiAnalysisEngine().analyze(object())  # type: ignore[arg-type]


def test_no_javascript_or_schema_is_generated():
    spec = _parse_openapi(
        {"/pets": {"post": {"responses": {"201": {"description": "Criado"}}}}}
    )

    result = ApiAnalysisEngine().analyze(spec)

    assert not hasattr(result, "script")
    assert not hasattr(result, "javascript")
    assert not hasattr(result.endpoints[0], "schema")


def test_analyzing_collection_does_not_generate_unknown_item_warning_for_valid_items():
    document = _parse_collection(
        [{"name": "R1", "request": {"method": "GET", "url": "https://x/y"}}]
    )

    result = ApiAnalysisEngine().analyze(document)

    assert not any(w.code == "UNKNOWN_ITEM_SKIPPED" for w in result.warnings)


def test_unknown_collection_item_generates_warning_and_is_skipped():
    document = _parse_collection(
        [
            {"name": "Item estranho", "somethingElse": True},
            {"name": "R1", "request": {"method": "GET", "url": "https://x/y"}},
        ]
    )

    result = ApiAnalysisEngine().analyze(document)

    assert len(result.endpoints) == 1
    assert any(w.code == "UNKNOWN_ITEM_SKIPPED" for w in result.warnings)
