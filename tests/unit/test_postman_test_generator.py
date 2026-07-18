from api_quality_agent.domain.models import (
    EndpointAnalysis,
    TestStrategyOptions,
)
from api_quality_agent.domain.services import TestStrategyEngine
from api_quality_agent.generators import PostmanTestGenerator, is_valid_javascript_syntax


def _build_endpoint(
    *,
    source="GET /pets",
    method="GET",
    path="/pets",
    response_status_codes=(),
    response_content_types=(),
) -> EndpointAnalysis:
    return EndpointAnalysis(
        source=source,
        method=method,
        path=path,
        operation_id=None,
        parameters=(),
        has_request_body=False,
        request_content_types=(),
        response_status_codes=response_status_codes,
        response_content_types=response_content_types,
        auth_type=None,
        variables_used=(),
        has_examples=False,
        example_count=0,
    )


# --- Snapshot do JavaScript gerado ----------------------------------------------

_SNAPSHOT_SCRIPT = (
    "// O corpo da resposta é interpretado uma única vez e reutilizado pelos testes abaixo.\n"
    "var responseBody;\n"
    "var responseBodyParseError = null;\n"
    "try {\n"
    "    responseBody = pm.response.json();\n"
    "} catch (error) {\n"
    "    responseBodyParseError = error;\n"
    "}\n"
    "\n"
    'pm.test("Status code da resposta deve ser 200.", function () {\n'
    "    pm.response.to.have.status(200);\n"
    "});\n"
    "\n"
    'pm.test("Content-Type da resposta deve conter \'application/json\'.", function () {\n'
    '    var actualContentType = pm.response.headers.get("Content-Type") || "";\n'
    '    pm.expect(actualContentType).to.include("application/json");\n'
    "});\n"
    "\n"
    'pm.test("O corpo da resposta deve ser um JSON válido.", function () {\n'
    '    pm.expect(responseBodyParseError, responseBodyParseError ? String(responseBodyParseError) : "").to.be.null;\n'
    "});\n"
    "\n"
    'pm.test("O corpo da resposta deve validar contra o schema esperado.", function () {\n'
    '    pm.response.to.have.jsonSchema({"type": "object", "properties": {"id": {"type": "integer"}, "name": {"type": "string"}}, "required": ["id"]});\n'
    "});\n"
    "\n"
    'pm.test("A resposta não deve conter propriedades além das declaradas no schema.", function () {\n'
    '    var allowedProperties = ["id", "name"];\n'
    "    var actualProperties = Object.keys(responseBody);\n"
    "    var extraProperties = actualProperties.filter(function (key) { return allowedProperties.indexOf(key) === -1; });\n"
    '    pm.expect(extraProperties, "Propriedades inesperadas: " + extraProperties.join(", ")).to.have.lengthOf(0);\n'
    "});\n"
    "\n"
    'pm.test("O campo obrigatório \'id\' deve estar presente na resposta.", function () {\n'
    '    pm.expect(responseBody).to.have.property("id");\n'
    "});\n"
    "\n"
    'if (responseBody && typeof responseBody === "object" && Object.prototype.hasOwnProperty.call(responseBody, "id")) {\n'
    '    pm.collectionVariables.set("id", responseBody["id"]);\n'
    "}\n"
)


def test_generated_script_matches_snapshot():
    endpoint = _build_endpoint(
        response_status_codes=("200",), response_content_types=("application/json",)
    )
    response_schema = {
        "type": "object",
        "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
        "required": ["id"],
    }
    strategy = TestStrategyEngine().build_strategy(
        endpoint,
        response_schema=response_schema,
        options=TestStrategyOptions(assert_no_extra_properties=True),
    )

    script = PostmanTestGenerator().generate(strategy)

    assert script == _SNAPSHOT_SCRIPT


# --- Objeto ----------------------------------------------------------------------


def test_object_response_generates_required_field_and_no_extra_properties():
    endpoint = _build_endpoint(
        response_status_codes=("200",), response_content_types=("application/json",)
    )
    response_schema = {
        "type": "object",
        "properties": {"id": {"type": "integer"}},
        "required": ["id"],
    }
    strategy = TestStrategyEngine().build_strategy(
        endpoint,
        response_schema=response_schema,
        options=TestStrategyOptions(assert_no_extra_properties=True),
    )

    script = PostmanTestGenerator().generate(strategy)

    assert 'pm.expect(responseBody).to.have.property("id");' in script
    assert "allowedProperties" in script
    assert 'to.be.an("array")' not in script


# --- Array -------------------------------------------------------------------------


def test_array_response_generates_array_not_empty_assertion():
    endpoint = _build_endpoint(
        response_status_codes=("200",), response_content_types=("application/json",)
    )
    array_schema = {"type": "array", "items": {"type": "object"}}
    strategy = TestStrategyEngine().build_strategy(
        endpoint,
        response_schema=array_schema,
        options=TestStrategyOptions(assert_array_not_empty=True),
    )

    script = PostmanTestGenerator().generate(strategy)

    assert 'pm.expect(responseBody).to.be.an("array").that.is.not.empty;' in script
    assert "hasOwnProperty" not in script
    assert "allowedProperties" not in script


# --- Sem body ----------------------------------------------------------------------


def test_no_body_related_assertions_do_not_generate_parse_block():
    endpoint = _build_endpoint(
        source="DELETE /pets/1",
        method="DELETE",
        response_status_codes=("204",),
    )

    strategy = TestStrategyEngine().build_strategy(endpoint)
    script = PostmanTestGenerator().generate(strategy)

    assert "pm.response.json()" not in script
    assert "responseBody" not in script
    assert 'pm.test("Status code da resposta deve ser 204.", function () {' in script


# --- Status e header --------------------------------------------------------------


def test_status_and_content_type_assertions_are_generated():
    endpoint = _build_endpoint(
        response_status_codes=("201",), response_content_types=("application/json",)
    )

    strategy = TestStrategyEngine().build_strategy(endpoint)
    script = PostmanTestGenerator().generate(strategy)

    assert "pm.response.to.have.status(201);" in script
    assert 'pm.response.headers.get("Content-Type")' in script
    assert 'to.include("application/json")' in script


# --- Schema --------------------------------------------------------------------------


def test_schema_assertion_embeds_exact_schema_as_json():
    endpoint = _build_endpoint(
        response_status_codes=("200",), response_content_types=("application/json",)
    )
    response_schema = {"type": "object", "properties": {"id": {"type": "integer"}}}

    strategy = TestStrategyEngine().build_strategy(endpoint, response_schema=response_schema)
    script = PostmanTestGenerator().generate(strategy)

    assert (
        'pm.response.to.have.jsonSchema({"type": "object", "properties": {"id": {"type": "integer"}}});'
        in script
    )


# --- Extração de variável ----------------------------------------------------------


def test_variable_extraction_uses_configured_scope():
    endpoint = _build_endpoint(
        response_status_codes=("201",), response_content_types=("application/json",)
    )
    response_schema = {"type": "object", "properties": {"id": {"type": "integer"}}}

    strategy = TestStrategyEngine().build_strategy(endpoint, response_schema=response_schema)
    script = PostmanTestGenerator().generate(strategy)

    assert "pm.collectionVariables.set(\"id\", responseBody[\"id\"]);" in script
    assert 'hasOwnProperty.call(responseBody, "id")' in script


# --- Required ------------------------------------------------------------------------


def test_required_field_with_must_have_value_generates_extra_assertion():
    endpoint = _build_endpoint(
        response_status_codes=("200",), response_content_types=("application/json",)
    )
    response_schema = {
        "type": "object",
        "properties": {"id": {"type": "integer"}},
        "required": ["id"],
    }

    strategy = TestStrategyEngine().build_strategy(
        endpoint,
        response_schema=response_schema,
        options=TestStrategyOptions(assert_required_has_value=True),
    )
    script = PostmanTestGenerator().generate(strategy)

    assert 'pm.expect(responseBody).to.have.property("id");' in script
    assert 'to.not.be.oneOf([null, undefined, ""])' in script


# --- Propriedades extras ----------------------------------------------------------


def test_no_extra_properties_lists_allowed_properties_from_schema():
    endpoint = _build_endpoint(
        response_status_codes=("200",), response_content_types=("application/json",)
    )
    response_schema = {
        "type": "object",
        "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
    }

    strategy = TestStrategyEngine().build_strategy(
        endpoint,
        response_schema=response_schema,
        options=TestStrategyOptions(assert_no_extra_properties=True),
    )
    script = PostmanTestGenerator().generate(strategy)

    assert 'var allowedProperties = ["id", "name"];' in script


# --- Sintaxe válida ------------------------------------------------------------------


def test_generated_scripts_are_syntactically_valid_javascript():
    scenarios = []

    endpoint_object = _build_endpoint(
        response_status_codes=("200",), response_content_types=("application/json",)
    )
    object_schema = {
        "type": "object",
        "properties": {"id": {"type": "integer"}, "tags": {"type": "array"}},
        "required": ["id"],
    }
    scenarios.append(
        TestStrategyEngine().build_strategy(
            endpoint_object,
            response_schema=object_schema,
            options=TestStrategyOptions(
                assert_no_extra_properties=True,
                assert_required_has_value=True,
                max_response_time_ms=300,
            ),
        )
    )

    endpoint_array = _build_endpoint(
        response_status_codes=("200",), response_content_types=("application/json",)
    )
    array_schema = {"type": "array", "items": {"type": "string"}}
    scenarios.append(
        TestStrategyEngine().build_strategy(
            endpoint_array,
            response_schema=array_schema,
            options=TestStrategyOptions(assert_array_not_empty=True),
        )
    )

    endpoint_no_content = _build_endpoint(
        source="DELETE /pets/1", method="DELETE", response_status_codes=("204",)
    )
    scenarios.append(TestStrategyEngine().build_strategy(endpoint_no_content))

    generator = PostmanTestGenerator()
    for strategy in scenarios:
        script = generator.generate(strategy)
        assert is_valid_javascript_syntax(script), script


def test_syntax_validator_rejects_broken_script():
    broken_script = 'pm.test("a", function () { pm.response.to.have.status(200); '

    assert is_valid_javascript_syntax(broken_script) is False


def test_syntax_validator_accepts_braces_inside_string_literals():
    script = 'var x = "{ not a real brace }";'

    assert is_valid_javascript_syntax(script) is True


# --- Idempotência da geração ---------------------------------------------------------


def test_generation_is_idempotent_for_the_same_strategy():
    endpoint = _build_endpoint(
        response_status_codes=("200",), response_content_types=("application/json",)
    )
    response_schema = {
        "type": "object",
        "properties": {"id": {"type": "integer"}},
        "required": ["id"],
    }
    strategy = TestStrategyEngine().build_strategy(endpoint, response_schema=response_schema)
    generator = PostmanTestGenerator()

    first = generator.generate(strategy)
    second = generator.generate(strategy)

    assert first == second


# --- Segurança / não conhece a API do Postman ------------------------------------------


def test_generator_module_has_no_postman_adapter_dependency():
    import api_quality_agent.generators.postman_test_generator as module

    source = module.__file__
    assert source is not None
    with open(source, encoding="utf-8") as handle:
        content = handle.read()
    assert "adapters.postman" not in content
    assert "requests" not in content
    assert "httpx" not in content
