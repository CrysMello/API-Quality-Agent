import json
import re
from collections.abc import Callable
from typing import Any

from api_quality_agent.domain.models import (
    AssertionDefinition,
    AssertionType,
    TestStrategy,
    VariableExtraction,
    VariableScope,
)

_BODY_RELATED_ASSERTION_TYPES = frozenset(
    {
        AssertionType.VALID_JSON_BODY,
        AssertionType.SCHEMA,
        AssertionType.ARRAY_NOT_EMPTY,
        AssertionType.NO_EXTRA_PROPERTIES,
        AssertionType.REQUIRED_FIELD_PRESENT,
    }
)

_SCOPE_ACCESSOR: dict[VariableScope, str] = {
    VariableScope.COLLECTION: "pm.collectionVariables",
    VariableScope.ENVIRONMENT: "pm.environment",
    VariableScope.LOCAL: "pm.variables",
}

_UNSAFE_VARIABLE_NAME_CHARS = re.compile(r"[^A-Za-z0-9_\-]")

_JSON_PATH_FIELD_PATTERN = re.compile(r"^\$\.([A-Za-z0-9_\-]+)$")


def _js_literal(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


class PostmanTestGenerator:
    def generate(self, strategy: TestStrategy) -> str:
        response_schema = _extract_response_schema(strategy)
        blocks: list[str] = []

        if _needs_response_body(strategy):
            blocks.append(_render_body_parse_block())

        for assertion in strategy.assertions:
            if not assertion.enabled:
                continue
            renderer = _ASSERTION_RENDERERS.get(assertion.assertion_type)
            if renderer is None:
                continue
            blocks.append(renderer(assertion, response_schema))

        for extraction in strategy.variable_extractions:
            blocks.append(_render_variable_extraction(extraction))

        return "\n\n".join(blocks).rstrip() + "\n"


def _needs_response_body(strategy: TestStrategy) -> bool:
    if any(a.assertion_type in _BODY_RELATED_ASSERTION_TYPES for a in strategy.assertions):
        return True
    return bool(strategy.variable_extractions)


def _extract_response_schema(strategy: TestStrategy) -> dict[str, Any] | None:
    for assertion in strategy.assertions:
        if assertion.assertion_type == AssertionType.SCHEMA:
            return assertion.expected_value
    return None


def _render_body_parse_block() -> str:
    return (
        "// O corpo da resposta é interpretado uma única vez e reutilizado pelos testes abaixo.\n"
        "var responseBody;\n"
        "var responseBodyParseError = null;\n"
        "try {\n"
        "    responseBody = pm.response.json();\n"
        "} catch (error) {\n"
        "    responseBodyParseError = error;\n"
        "}"
    )


def _wrap_test(name: str, body_lines: list[str]) -> str:
    indented_body = "\n".join(f"    {line}" for line in body_lines)
    return f"pm.test({_js_literal(name)}, function () {{\n{indented_body}\n}});"


def _render_status_code(assertion: AssertionDefinition, _schema: dict[str, Any] | None) -> str:
    status_code = int(assertion.expected_value)
    return _wrap_test(assertion.description, [f"pm.response.to.have.status({status_code});"])


def _render_content_type(assertion: AssertionDefinition, _schema: dict[str, Any] | None) -> str:
    content_type = str(assertion.expected_value)
    return _wrap_test(
        assertion.description,
        [
            'var actualContentType = pm.response.headers.get("Content-Type") || "";',
            f"pm.expect(actualContentType).to.include({_js_literal(content_type)});",
        ],
    )


def _render_response_time(assertion: AssertionDefinition, _schema: dict[str, Any] | None) -> str:
    max_response_time_ms = int(assertion.expected_value)
    return _wrap_test(
        assertion.description,
        [f"pm.expect(pm.response.responseTime).to.be.below({max_response_time_ms});"],
    )


def _render_valid_json_body(assertion: AssertionDefinition, _schema: dict[str, Any] | None) -> str:
    return _wrap_test(
        assertion.description,
        [
            "pm.expect(responseBodyParseError, "
            'responseBodyParseError ? String(responseBodyParseError) : "").to.be.null;'
        ],
    )


def _render_schema(assertion: AssertionDefinition, _schema: dict[str, Any] | None) -> str:
    schema_literal = _js_literal(assertion.expected_value)
    return _wrap_test(assertion.description, [f"pm.response.to.have.jsonSchema({schema_literal});"])


def _render_array_not_empty(assertion: AssertionDefinition, _schema: dict[str, Any] | None) -> str:
    return _wrap_test(
        assertion.description,
        ['pm.expect(responseBody).to.be.an("array").that.is.not.empty;'],
    )


def _render_no_extra_properties(
    assertion: AssertionDefinition, schema: dict[str, Any] | None
) -> str:
    allowed_properties = list((schema or {}).get("properties", {}).keys())
    return _wrap_test(
        assertion.description,
        [
            f"var allowedProperties = {_js_literal(allowed_properties)};",
            "var actualProperties = Object.keys(responseBody);",
            "var extraProperties = actualProperties.filter(function (key) {"
            " return allowedProperties.indexOf(key) === -1; });",
            'pm.expect(extraProperties, "Propriedades inesperadas: " + '
            "extraProperties.join(\", \")).to.have.lengthOf(0);",
        ],
    )


def _render_required_field_present(
    assertion: AssertionDefinition, _schema: dict[str, Any] | None
) -> str:
    info = assertion.expected_value
    field = str(info["field"])
    field_literal = _js_literal(field)
    lines = [f"pm.expect(responseBody).to.have.property({field_literal});"]
    if info.get("must_have_value"):
        message = _js_literal(f"'{field}' não deve ser vazio")
        lines.append(
            f"pm.expect(responseBody[{field_literal}], {message})"
            ".to.not.be.oneOf([null, undefined, \"\"]);"
        )
    return _wrap_test(assertion.description, lines)


_ASSERTION_RENDERERS: dict[
    AssertionType, Callable[[AssertionDefinition, dict[str, Any] | None], str]
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


def _sanitize_variable_name(name: str) -> str:
    sanitized = _UNSAFE_VARIABLE_NAME_CHARS.sub("_", name)
    return sanitized or "variable"


def _json_path_to_field(json_path: str) -> str:
    match = _JSON_PATH_FIELD_PATTERN.match(json_path)
    if match is None:
        raise ValueError(f"JSON path não suportado pelo gerador: {json_path!r}")
    return match.group(1)


def _render_variable_extraction(extraction: VariableExtraction) -> str:
    accessor = _SCOPE_ACCESSOR[extraction.scope]
    field = _json_path_to_field(extraction.json_path)
    field_literal = _js_literal(field)
    variable_literal = _js_literal(_sanitize_variable_name(extraction.variable_name))
    return (
        f'if (responseBody && typeof responseBody === "object" && '
        f"Object.prototype.hasOwnProperty.call(responseBody, {field_literal})) {{\n"
        f"    {accessor}.set({variable_literal}, responseBody[{field_literal}]);\n"
        f"}}"
    )
