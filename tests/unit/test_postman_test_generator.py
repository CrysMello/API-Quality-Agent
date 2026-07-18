from api_quality_agent.domain.models import EndpointAnalysis, TestStrategyOptions
from api_quality_agent.domain.services import TestStrategyEngine
from api_quality_agent.generators import (
    GeneratedTestScript,
    PostmanTestGenerator,
    TestCategory,
    format_test_script_preview,
    is_valid_javascript_syntax,
)


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


def _assertion_of_category(result: GeneratedTestScript, category: TestCategory):
    return next(item for item in result.summary if item.category == category)


def _summary_item(result: GeneratedTestScript, test_id: str):
    return next(item for item in result.summary if item.test_id == test_id)


# --- Status code com comentário --------------------------------------------------


def test_status_code_generates_comment_and_test():
    endpoint = _build_endpoint(response_status_codes=("200",))
    strategy = TestStrategyEngine().build_strategy(endpoint)

    result = PostmanTestGenerator().generate(strategy)

    assert "// Validação: o endpoint deve retornar HTTP 200." in result.script
    assert 'pm.test("Status code é 200", function () {' in result.script
    item = _assertion_of_category(result, TestCategory.STATUS_CODE)
    assert item.test_id == "status-code-200"
    assert item.title == "Status code é 200"


# --- Content-Type com comentário --------------------------------------------------


def test_content_type_generates_comment_and_test():
    endpoint = _build_endpoint(
        response_status_codes=("200",), response_content_types=("application/json",)
    )
    strategy = TestStrategyEngine().build_strategy(endpoint)

    result = PostmanTestGenerator().generate(strategy)

    assert "// Validação: a resposta deve possuir Content-Type application/json." in result.script
    assert 'pm.test("Content-Type é JSON", function () {' in result.script
    item = _assertion_of_category(result, TestCategory.CONTENT_TYPE)
    assert item.description == "Valida que a resposta possui Content-Type application/json."


# --- Tempo de resposta com comentário ----------------------------------------------


def test_response_time_generates_comment_and_test():
    endpoint = _build_endpoint(response_status_codes=("200",))
    strategy = TestStrategyEngine().build_strategy(
        endpoint, options=TestStrategyOptions(max_response_time_ms=500)
    )

    result = PostmanTestGenerator().generate(strategy)

    assert "// Validação: o tempo da resposta deve ser menor que 500 ms." in result.script
    assert 'pm.test("Tempo de resposta menor que 500 ms", function () {' in result.script
    item = _assertion_of_category(result, TestCategory.RESPONSE_TIME)
    assert item.source == "configuration"


# --- Campo obrigatório com comentário -----------------------------------------------


def test_required_field_without_known_type_generates_presence_only_test():
    endpoint = _build_endpoint(
        response_status_codes=("200",), response_content_types=("application/json",)
    )
    response_schema = {
        "type": "object",
        "properties": {"metadata": {"type": "object"}},
        "required": ["metadata"],
    }
    strategy = TestStrategyEngine().build_strategy(endpoint, response_schema=response_schema)

    result = PostmanTestGenerator().generate(strategy)

    assert '// Validação: o campo "metadata" é obrigatório e deve existir na resposta.' in result.script
    assert 'pm.test("Campo metadata é obrigatório", function () {' in result.script
    item = _assertion_of_category(result, TestCategory.REQUIRED_FIELD)
    assert item.test_id == "required-field-metadata"


# --- Tipo de campo com comentário ---------------------------------------------------


def test_required_field_with_known_type_combines_presence_and_type():
    endpoint = _build_endpoint(
        response_status_codes=("200",), response_content_types=("application/json",)
    )
    response_schema = {
        "type": "object",
        "properties": {"id": {"type": "integer"}},
        "required": ["id"],
    }
    strategy = TestStrategyEngine().build_strategy(endpoint, response_schema=response_schema)

    result = PostmanTestGenerator().generate(strategy)

    assert '// Validação: o campo "id" é obrigatório e deve ser numérico.' in result.script
    assert 'pm.test("Campo id é obrigatório e numérico", function () {' in result.script
    assert '.to.have.property("id")' in result.script
    assert '.that.is.a("number");' in result.script
    item = _assertion_of_category(result, TestCategory.FIELD_TYPE)
    assert item.test_id == "field-type-id-number"
    assert item.description == 'Valida que o campo "id" possui o tipo number.'


def test_ambiguous_field_type_falls_back_to_presence_and_generates_warning():
    endpoint = _build_endpoint(
        response_status_codes=("200",), response_content_types=("application/json",)
    )
    response_schema = {
        "type": "object",
        "properties": {"tag": {"type": ["string", "null"]}},
        "required": ["tag"],
    }
    strategy = TestStrategyEngine().build_strategy(endpoint, response_schema=response_schema)

    result = PostmanTestGenerator().generate(strategy)

    assert 'pm.test("Campo tag é obrigatório", function () {' in result.script
    assert any(w.code == "AMBIGUOUS_FIELD_TYPE" for w in result.warnings)


# --- Array com comentário -----------------------------------------------------------


def test_array_not_empty_generates_comment_and_test():
    endpoint = _build_endpoint(
        response_status_codes=("200",), response_content_types=("application/json",)
    )
    array_schema = {"type": "array", "items": {"type": "object"}}
    strategy = TestStrategyEngine().build_strategy(
        endpoint,
        response_schema=array_schema,
        options=TestStrategyOptions(assert_array_not_empty=True),
    )

    result = PostmanTestGenerator().generate(strategy)

    assert "// Validação: a resposta deve ser uma lista não vazia." in result.script
    assert 'pm.test("Resposta contém uma lista não vazia", function () {' in result.script
    item = _assertion_of_category(result, TestCategory.ARRAY_STRUCTURE)
    assert item.test_id == "array-not-empty"


# --- Schema com comentário -----------------------------------------------------------


def test_schema_generates_comment_and_embedded_json_schema():
    endpoint = _build_endpoint(
        response_status_codes=("200",), response_content_types=("application/json",)
    )
    response_schema = {"type": "object", "properties": {"id": {"type": "integer"}}}
    strategy = TestStrategyEngine().build_strategy(endpoint, response_schema=response_schema)

    result = PostmanTestGenerator().generate(strategy)

    assert "// Validação: o corpo da resposta deve corresponder ao schema esperado." in result.script
    assert (
        'pm.response.to.have.jsonSchema({"type": "object", "properties": {"id": {"type": "integer"}}});'
        in result.script
    )
    item = _summary_item(result, "response-matches-schema")
    assert item.category == TestCategory.JSON_SCHEMA


# --- Extração de variável com comentário --------------------------------------------


def test_variable_extraction_generates_comment_and_review_warning():
    endpoint = _build_endpoint(
        response_status_codes=("201",), response_content_types=("application/json",)
    )
    response_schema = {"type": "object", "properties": {"id": {"type": "integer"}}}
    strategy = TestStrategyEngine().build_strategy(endpoint, response_schema=response_schema)

    result = PostmanTestGenerator().generate(strategy)

    assert (
        '// Validação: extrai o valor do campo "id" para reutilização em requests futuras.'
        in result.script
    )
    assert 'pm.collectionVariables.set("id", body["id"]);' in result.script
    item = _assertion_of_category(result, TestCategory.VARIABLE_EXTRACTION)
    assert item.test_id == "variable-extraction-id"
    assert any(
        w.code == "VARIABLE_EXTRACTION_REQUIRES_REVIEW" and w.test_id == "variable-extraction-id"
        for w in result.warnings
    )


# --- Comentário sem segredo -----------------------------------------------------------


def test_comments_and_summary_never_contain_sensitive_values():
    endpoint = _build_endpoint(
        response_status_codes=("200",), response_content_types=("application/json",)
    )
    response_schema = {
        "type": "object",
        "properties": {"token": {"type": "string"}},
        "required": ["token"],
    }
    strategy = TestStrategyEngine().build_strategy(endpoint, response_schema=response_schema)

    result = PostmanTestGenerator().generate(strategy)

    forbidden_values = ("super-secret-token-value", "sk_live_", "password123")
    for forbidden in forbidden_values:
        assert forbidden not in result.script
    for item in result.summary:
        for forbidden in forbidden_values:
            assert forbidden not in item.title
            assert forbidden not in item.description


# --- Nome do pm.test claro -----------------------------------------------------------


def test_test_names_are_specific_not_generic():
    endpoint = _build_endpoint(
        response_status_codes=("200",), response_content_types=("application/json",)
    )
    response_schema = {
        "type": "object",
        "properties": {"id": {"type": "integer"}},
        "required": ["id"],
    }
    strategy = TestStrategyEngine().build_strategy(endpoint, response_schema=response_schema)

    result = PostmanTestGenerator().generate(strategy)

    generic_names = {"Teste 1", "Validação", "Schema", "Campo"}
    titles = {item.title for item in result.summary}
    assert titles.isdisjoint(generic_names)
    for title in titles:
        assert len(title) > 5


# --- Correspondência entre resumo e testes / test_count ------------------------------


def test_summary_matches_generated_tests_and_count():
    endpoint = _build_endpoint(
        response_status_codes=("200",), response_content_types=("application/json",)
    )
    response_schema = {
        "type": "object",
        "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
        "required": ["id", "name"],
    }
    strategy = TestStrategyEngine().build_strategy(
        endpoint,
        response_schema=response_schema,
        options=TestStrategyOptions(max_response_time_ms=500),
    )

    result = PostmanTestGenerator().generate(strategy)

    assert result.test_count == len(result.summary)
    test_ids = {item.test_id for item in result.summary}
    assert len(test_ids) == len(result.summary)
    for item in result.summary:
        if item.category is TestCategory.VARIABLE_EXTRACTION:
            continue
        assert item.title in result.script
    assert result.script.count("pm.test(") + result.script.count("if (body") == result.test_count


# --- Script e resumo determinísticos --------------------------------------------------


def test_script_and_summary_are_deterministic():
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

    assert first.script == second.script
    assert first.summary == second.summary
    assert first.warnings == second.warnings
    assert first.test_count == second.test_count


# --- Ausência/presença da declaração de body ------------------------------------------


def test_no_body_declaration_when_not_needed():
    endpoint = _build_endpoint(source="DELETE /pets/1", method="DELETE", response_status_codes=("204",))
    strategy = TestStrategyEngine().build_strategy(endpoint)

    result = PostmanTestGenerator().generate(strategy)

    assert "pm.response.json()" not in result.script
    assert "body" not in result.script


def test_single_body_declaration_when_multiple_tests_need_it():
    endpoint = _build_endpoint(
        response_status_codes=("200",), response_content_types=("application/json",)
    )
    response_schema = {
        "type": "object",
        "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
        "required": ["id", "name"],
    }
    strategy = TestStrategyEngine().build_strategy(endpoint, response_schema=response_schema)

    result = PostmanTestGenerator().generate(strategy)

    assert result.script.count("pm.response.json()") == 1
    assert result.script.count("let body;") == 1


# --- Warning para inferência incerta --------------------------------------------------


def test_expected_status_not_defined_warning_when_status_is_ambiguous():
    endpoint = _build_endpoint(response_status_codes=())
    strategy = TestStrategyEngine().build_strategy(endpoint)

    result = PostmanTestGenerator().generate(strategy)

    assert any(w.code == "EXPECTED_STATUS_NOT_DEFINED" for w in result.warnings)
    assert "pm.response.to.have.status" not in result.script


# --- Ausência de alteração na entrada --------------------------------------------------


def test_strategy_is_not_mutated_by_generation():
    endpoint = _build_endpoint(
        response_status_codes=("200",), response_content_types=("application/json",)
    )
    response_schema = {
        "type": "object",
        "properties": {"id": {"type": "integer"}},
        "required": ["id"],
    }
    strategy = TestStrategyEngine().build_strategy(endpoint, response_schema=response_schema)
    original_assertions = strategy.assertions
    original_extractions = strategy.variable_extractions

    PostmanTestGenerator().generate(strategy)

    assert strategy.assertions == original_assertions
    assert strategy.variable_extractions == original_extractions


# --- Compatibilidade com o Managed Block Merger -----------------------------------------


def test_script_field_is_plain_string_usable_for_merge():
    endpoint = _build_endpoint(response_status_codes=("200",))
    strategy = TestStrategyEngine().build_strategy(endpoint)

    result = PostmanTestGenerator().generate(strategy)

    assert isinstance(result.script, str)
    assert "GeneratedTestSummaryItem" not in result.script
    assert "GenerationWarning" not in result.script


# --- Sintaxe válida --------------------------------------------------------------------


def test_generated_script_is_syntactically_valid_javascript():
    endpoint = _build_endpoint(
        response_status_codes=("200",), response_content_types=("application/json",)
    )
    response_schema = {
        "type": "object",
        "properties": {"id": {"type": "integer"}, "tags": {"type": "array"}},
        "required": ["id"],
    }
    strategy = TestStrategyEngine().build_strategy(
        endpoint,
        response_schema=response_schema,
        options=TestStrategyOptions(
            assert_no_extra_properties=True, max_response_time_ms=300
        ),
    )

    result = PostmanTestGenerator().generate(strategy)

    assert is_valid_javascript_syntax(result.script), result.script


# --- Preview do CLI ----------------------------------------------------------------------


def test_preview_formatter_renders_title_and_description():
    endpoint = _build_endpoint(response_status_codes=("200",))
    strategy = TestStrategyEngine().build_strategy(endpoint)
    result = PostmanTestGenerator().generate(strategy)

    preview = format_test_script_preview(result, request_label="GET /pets")

    assert "Request: GET /pets" in preview
    assert f"Testes que serão gerados: {result.test_count}" in preview
    assert "1. Status code é 200" in preview
    assert "   Valida que o endpoint retorna HTTP 200." in preview


# --- Teste de exemplo completo (cenário do prompt) ---------------------------------------


def test_full_example_scenario_get_users_id():
    endpoint = _build_endpoint(
        source="GET /users/{id}",
        method="GET",
        path="/users/{id}",
        response_status_codes=("200",),
        response_content_types=("application/json",),
    )
    response_schema = {
        "type": "object",
        "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
        "required": ["id", "name"],
    }
    strategy = TestStrategyEngine().build_strategy(
        endpoint,
        response_schema=response_schema,
        options=TestStrategyOptions(max_response_time_ms=500),
    )

    result = PostmanTestGenerator().generate(strategy)

    titles = [item.title for item in result.summary]
    assert "Status code é 200" in titles
    assert "Content-Type é JSON" in titles
    assert "Campo id é obrigatório e numérico" in titles
    assert "Campo name é obrigatório e textual" in titles
    assert "Tempo de resposta menor que 500 ms" in titles

    assert is_valid_javascript_syntax(result.script)
    assert result.script.count("let body;") == 1
    assert result.test_count == len(result.summary)
