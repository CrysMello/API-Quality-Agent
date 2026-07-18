import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from api_quality_agent.domain.models import (
    AssertionDefinition,
    AssertionType,
    TestStrategy,
    VariableExtraction,
    VariableScope,
)
from api_quality_agent.generators.generated_test_script import GeneratedTestScript
from api_quality_agent.generators.generated_test_summary_item import GeneratedTestSummaryItem
from api_quality_agent.generators.generation_warning import GenerationWarning
from api_quality_agent.generators.test_category import TestCategory

_SCOPE_ACCESSOR: dict[VariableScope, str] = {
    VariableScope.COLLECTION: "pm.collectionVariables",
    VariableScope.ENVIRONMENT: "pm.environment",
    VariableScope.LOCAL: "pm.variables",
}

_SIMPLE_TYPE_LABELS: dict[str, tuple[str, str]] = {
    "string": ("textual", "string"),
    "integer": ("numérico", "number"),
    "number": ("numérico", "number"),
    "boolean": ("booleano", "boolean"),
}

_UNSAFE_VARIABLE_NAME_CHARS = re.compile(r"[^A-Za-z0-9_\-]")
_JSON_PATH_FIELD_PATTERN = re.compile(r"^\$\.([A-Za-z0-9_\-]+)$")
_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def _js_literal(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _make_test_id(*parts: str) -> str:
    slugs = [slug for part in parts if (slug := _SLUG_PATTERN.sub("-", part.lower()).strip("-"))]
    return "-".join(slugs)


@dataclass
class _RenderedTest:
    test_id: str
    title: str
    description: str
    category: TestCategory
    source: str | None
    comment_lines: tuple[str, ...]
    statements: tuple[str, ...]
    uses_response_body: bool
    is_assertion_block: bool = True


class PostmanTestGenerator:
    def generate(self, strategy: TestStrategy) -> GeneratedTestScript:
        response_schema = _extract_response_schema(strategy)
        warnings: list[GenerationWarning] = _translate_strategy_warnings(strategy)

        rendered_tests: list[_RenderedTest] = []
        for assertion in strategy.assertions:
            if not assertion.enabled:
                continue
            renderer = _ASSERTION_RENDERERS.get(assertion.assertion_type)
            if renderer is None:
                warnings.append(
                    GenerationWarning(
                        code="UNSUPPORTED_ASSERTION",
                        message=(
                            f"Tipo de asserção '{assertion.assertion_type.value}' não é "
                            "traduzido em JavaScript nesta etapa."
                        ),
                        test_id=None,
                        field=None,
                    )
                )
                continue
            rendered_tests.append(renderer(assertion, response_schema, warnings))

        for extraction in strategy.variable_extractions:
            rendered_tests.append(_render_variable_extraction(extraction, warnings))

        needs_body = any(test.uses_response_body for test in rendered_tests)

        blocks: list[str] = []
        if needs_body:
            blocks.append(_render_body_declaration())
        blocks.extend(_render_block(test) for test in rendered_tests)

        script = "\n\n".join(blocks).rstrip() + "\n"

        summary = tuple(
            GeneratedTestSummaryItem(
                test_id=test.test_id,
                title=test.title,
                description=test.description,
                category=test.category,
                source=test.source,
            )
            for test in rendered_tests
        )

        return GeneratedTestScript(
            script=script,
            summary=summary,
            test_count=len(rendered_tests),
            warnings=tuple(warnings),
        )


def _translate_strategy_warnings(strategy: TestStrategy) -> list[GenerationWarning]:
    translated: list[GenerationWarning] = []
    for warning in strategy.warnings:
        code = "EXPECTED_STATUS_NOT_DEFINED" if warning.code == "STATUS_CODE_AMBIGUOUS" else warning.code
        translated.append(
            GenerationWarning(code=code, message=warning.message, test_id=None, field=None)
        )
    return translated


def _extract_response_schema(strategy: TestStrategy) -> dict[str, Any] | None:
    for assertion in strategy.assertions:
        if assertion.assertion_type == AssertionType.SCHEMA:
            return assertion.expected_value
    return None


def _render_body_declaration() -> str:
    return (
        "// Interpreta o corpo da resposta como JSON para os testes que dependem dele.\n"
        "let body;\n"
        "try {\n"
        "    body = pm.response.json();\n"
        "} catch (error) {\n"
        "    body = undefined;\n"
        "}"
    )


def _render_block(rendered: _RenderedTest) -> str:
    comment = "\n".join(rendered.comment_lines)
    if rendered.is_assertion_block:
        indented_body = "\n".join(f"    {line}" if line else "" for line in rendered.statements)
        code = f"pm.test({_js_literal(rendered.title)}, function () {{\n{indented_body}\n}});"
    else:
        code = "\n".join(rendered.statements)
    return f"{comment}\n\n{code}"


# --- Renderers por tipo de asserção -------------------------------------------


def _render_status_code(
    assertion: AssertionDefinition, _schema: dict[str, Any] | None, _warnings: list[GenerationWarning]
) -> _RenderedTest:
    status = int(assertion.expected_value)
    return _RenderedTest(
        test_id=_make_test_id("status-code", str(status)),
        title=f"Status code é {status}",
        description=f"Valida que o endpoint retorna HTTP {status}.",
        category=TestCategory.STATUS_CODE,
        source=assertion.origin,
        comment_lines=(f"// Validação: o endpoint deve retornar HTTP {status}.",),
        statements=(f"pm.response.to.have.status({status});",),
        uses_response_body=False,
    )


def _render_content_type(
    assertion: AssertionDefinition, _schema: dict[str, Any] | None, _warnings: list[GenerationWarning]
) -> _RenderedTest:
    content_type = str(assertion.expected_value)
    title = (
        "Content-Type é JSON"
        if content_type == "application/json"
        else f"Content-Type contém '{content_type}'"
    )
    return _RenderedTest(
        test_id=_make_test_id("content-type", content_type),
        title=title,
        description=f"Valida que a resposta possui Content-Type {content_type}.",
        category=TestCategory.CONTENT_TYPE,
        source=assertion.origin,
        comment_lines=(f"// Validação: a resposta deve possuir Content-Type {content_type}.",),
        statements=(
            'const contentType = pm.response.headers.get("Content-Type");',
            "",
            f"pm.expect(contentType).to.include({_js_literal(content_type)});",
        ),
        uses_response_body=False,
    )


def _render_response_time(
    assertion: AssertionDefinition, _schema: dict[str, Any] | None, _warnings: list[GenerationWarning]
) -> _RenderedTest:
    max_response_time_ms = int(assertion.expected_value)
    return _RenderedTest(
        test_id=_make_test_id("response-time", str(max_response_time_ms)),
        title=f"Tempo de resposta menor que {max_response_time_ms} ms",
        description=f"Valida que o endpoint responde em menos de {max_response_time_ms} ms.",
        category=TestCategory.RESPONSE_TIME,
        source=assertion.origin,
        comment_lines=(
            f"// Validação: o tempo da resposta deve ser menor que {max_response_time_ms} ms.",
        ),
        statements=(f"pm.expect(pm.response.responseTime).to.be.below({max_response_time_ms});",),
        uses_response_body=False,
    )


def _render_valid_json_body(
    assertion: AssertionDefinition, _schema: dict[str, Any] | None, _warnings: list[GenerationWarning]
) -> _RenderedTest:
    return _RenderedTest(
        test_id="valid-json-body",
        title="Corpo da resposta é JSON válido",
        description="Valida que o corpo da resposta é um JSON bem formado.",
        category=TestCategory.JSON_SCHEMA,
        source=assertion.origin,
        comment_lines=("// Validação: o corpo da resposta deve ser um JSON válido.",),
        statements=(
            'pm.expect(body, "o corpo da resposta não é um JSON válido").to.not.be.undefined;',
        ),
        uses_response_body=True,
    )


def _render_schema(
    assertion: AssertionDefinition, _schema: dict[str, Any] | None, _warnings: list[GenerationWarning]
) -> _RenderedTest:
    schema_literal = _js_literal(assertion.expected_value)
    return _RenderedTest(
        test_id="response-matches-schema",
        title="Corpo da resposta corresponde ao schema esperado",
        description="Valida que o corpo da resposta corresponde à estrutura esperada.",
        category=TestCategory.JSON_SCHEMA,
        source=assertion.origin,
        comment_lines=("// Validação: o corpo da resposta deve corresponder ao schema esperado.",),
        statements=(f"pm.response.to.have.jsonSchema({schema_literal});",),
        uses_response_body=False,
    )


def _render_array_not_empty(
    assertion: AssertionDefinition, _schema: dict[str, Any] | None, _warnings: list[GenerationWarning]
) -> _RenderedTest:
    return _RenderedTest(
        test_id="array-not-empty",
        title="Resposta contém uma lista não vazia",
        description="Valida que a resposta é uma lista com pelo menos um item.",
        category=TestCategory.ARRAY_STRUCTURE,
        source=assertion.origin,
        comment_lines=("// Validação: a resposta deve ser uma lista não vazia.",),
        statements=('pm.expect(body).to.be.an("array").that.is.not.empty;',),
        uses_response_body=True,
    )


def _render_no_extra_properties(
    assertion: AssertionDefinition, schema: dict[str, Any] | None, _warnings: list[GenerationWarning]
) -> _RenderedTest:
    allowed_properties = list((schema or {}).get("properties", {}).keys())
    return _RenderedTest(
        test_id="no-extra-properties",
        title="Resposta não contém propriedades extras",
        description="Valida que a resposta não possui campos além dos declarados no schema.",
        category=TestCategory.JSON_SCHEMA,
        source=assertion.origin,
        comment_lines=(
            "// Validação: a resposta não deve conter propriedades além das declaradas no schema.",
        ),
        statements=(
            f"const allowedProperties = {_js_literal(allowed_properties)};",
            "const actualProperties = Object.keys(body);",
            "const extraProperties = actualProperties.filter(function (key) {"
            " return allowedProperties.indexOf(key) === -1; });",
            "",
            'pm.expect(extraProperties, "propriedades inesperadas: " + '
            'extraProperties.join(", ")).to.have.lengthOf(0);',
        ),
        uses_response_body=True,
    )


def _render_required_field_present(
    assertion: AssertionDefinition, schema: dict[str, Any] | None, warnings: list[GenerationWarning]
) -> _RenderedTest:
    info = assertion.expected_value
    field = str(info["field"])
    field_literal = _js_literal(field)

    field_schema = (schema or {}).get("properties", {}).get(field)
    field_type = field_schema.get("type") if isinstance(field_schema, dict) else None
    type_labels = _SIMPLE_TYPE_LABELS.get(field_type) if isinstance(field_type, str) else None

    if isinstance(field_type, list):
        warnings.append(
            GenerationWarning(
                code="AMBIGUOUS_FIELD_TYPE",
                message=(
                    f"Campo '{field}' possui tipo ambíguo ({field_type}); "
                    "apenas a presença será validada."
                ),
                test_id=_make_test_id("required-field", field),
                field=field,
            )
        )

    if type_labels is not None:
        label_pt, chai_type = type_labels
        title = f"Campo {field} é obrigatório e {label_pt}"
        description = f'Valida que o campo "{field}" possui o tipo {chai_type}.'
        comment_lines = (f'// Validação: o campo "{field}" é obrigatório e deve ser {label_pt}.',)
        statements: tuple[str, ...] = (
            "pm.expect(body)",
            f"    .to.have.property({field_literal})",
            f"    .that.is.a({_js_literal(chai_type)});",
        )
        category = TestCategory.FIELD_TYPE
        test_id = _make_test_id("field-type", field, chai_type)
    else:
        title = f"Campo {field} é obrigatório"
        description = f'Valida que a resposta contém o campo "{field}".'
        comment_lines = (
            f'// Validação: o campo "{field}" é obrigatório e deve existir na resposta.',
        )
        statements = (f"pm.expect(body).to.have.property({field_literal});",)
        category = TestCategory.REQUIRED_FIELD
        test_id = _make_test_id("required-field", field)

    if info.get("must_have_value"):
        message = _js_literal(f"'{field}' não deve ser vazio")
        statements = statements + (
            f"pm.expect(body[{field_literal}], {message})"
            '.to.not.be.oneOf([null, undefined, ""]);',
        )

    return _RenderedTest(
        test_id=test_id,
        title=title,
        description=description,
        category=category,
        source=assertion.origin,
        comment_lines=comment_lines,
        statements=statements,
        uses_response_body=True,
    )


_ASSERTION_RENDERERS: dict[
    AssertionType,
    Callable[[AssertionDefinition, dict[str, Any] | None, list[GenerationWarning]], _RenderedTest],
] = {
    AssertionType.STATUS_CODE: _render_status_code,
    AssertionType.CONTENT_TYPE: _render_content_type,
    AssertionType.RESPONSE_TIME: _render_response_time,
    AssertionType.VALID_JSON_BODY: _render_valid_json_body,
    AssertionType.SCHEMA: _render_schema,
    AssertionType.ARRAY_NOT_EMPTY: _render_array_not_empty,
    AssertionType.NO_EXTRA_PROPERTIES: _render_no_extra_properties,
    AssertionType.REQUIRED_FIELD_PRESENT: _render_required_field_present,
}


# --- Extração de variável -----------------------------------------------------


def _sanitize_variable_name(name: str) -> str:
    sanitized = _UNSAFE_VARIABLE_NAME_CHARS.sub("_", name)
    return sanitized or "variable"


def _json_path_to_field(json_path: str) -> str:
    match = _JSON_PATH_FIELD_PATTERN.match(json_path)
    if match is None:
        raise ValueError(f"JSON path não suportado pelo gerador: {json_path!r}")
    return match.group(1)


def _render_variable_extraction(
    extraction: VariableExtraction, warnings: list[GenerationWarning]
) -> _RenderedTest:
    accessor = _SCOPE_ACCESSOR[extraction.scope]
    field = _json_path_to_field(extraction.json_path)
    field_literal = _js_literal(field)
    variable_name = _sanitize_variable_name(extraction.variable_name)
    variable_literal = _js_literal(variable_name)
    test_id = _make_test_id("variable-extraction", extraction.variable_name)

    warnings.append(
        GenerationWarning(
            code="VARIABLE_EXTRACTION_REQUIRES_REVIEW",
            message=(
                f"A extração da variável '{extraction.variable_name}' é uma sugestão baseada "
                "no nome do campo; revise antes de usar."
            ),
            test_id=test_id,
            field=extraction.variable_name,
        )
    )

    return _RenderedTest(
        test_id=test_id,
        title=f"Extrai a variável {variable_name}",
        description=(
            f'Extrai o valor do campo "{field}" da resposta para a variável "{variable_name}".'
        ),
        category=TestCategory.VARIABLE_EXTRACTION,
        source=extraction.origin,
        comment_lines=(
            f'// Validação: extrai o valor do campo "{field}" para reutilização em requests futuras.',
        ),
        statements=(
            f'if (body && typeof body === "object" && '
            f"Object.prototype.hasOwnProperty.call(body, {field_literal})) {{",
            f"    {accessor}.set({variable_literal}, body[{field_literal}]);",
            "}",
        ),
        uses_response_body=True,
        is_assertion_block=False,
    )
