import re
from collections.abc import Sequence
from typing import Any

from api_quality_agent.domain.exceptions import InputError
from api_quality_agent.domain.models import SchemaInferencePolicy, SchemaInferenceResult, SchemaInferenceWarning

_ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _json_type_of(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    raise InputError(
        f"Tipo de valor não suportado para inferência de schema: {type(value).__name__}"
    )


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


class SchemaInferenceEngine:
    def infer(
        self,
        examples: Sequence[Any],
        *,
        policy: SchemaInferencePolicy | None = None,
        contractual_required: frozenset[str] | None = None,
    ) -> SchemaInferenceResult:
        if not examples:
            raise InputError("Nenhum exemplo fornecido para inferência de schema.")

        effective_policy = policy or SchemaInferencePolicy()
        warnings: list[SchemaInferenceWarning] = []

        node_schema = _infer_value_schema(
            list(examples),
            policy=effective_policy,
            warnings=warnings,
            path="$",
            contractual_required=contractual_required,
        )

        schema = {"$schema": effective_policy.schema_dialect, **node_schema}
        return SchemaInferenceResult(schema=schema, warnings=tuple(warnings))


def _infer_value_schema(
    values: list[Any],
    *,
    policy: SchemaInferencePolicy,
    warnings: list[SchemaInferenceWarning],
    path: str,
    contractual_required: frozenset[str] | None = None,
) -> dict[str, Any]:
    observed_types = _dedupe_preserve_order([_json_type_of(value) for value in values])

    if len(observed_types) > 1:
        non_null_types = [t for t in observed_types if t != "null"]
        if len(non_null_types) > 1:
            warnings.append(
                SchemaInferenceWarning(
                    code="INCONSISTENT_TYPE",
                    message=f"Tipos divergentes observados em '{path}': {sorted(observed_types)}.",
                    path=path,
                )
            )
        return {"type": sorted(observed_types)}

    json_type = observed_types[0]

    if json_type == "object":
        dict_values = [value for value in values if isinstance(value, dict)]
        return _infer_object_schema(
            dict_values,
            policy=policy,
            warnings=warnings,
            path=path,
            contractual_required=contractual_required,
        )

    if json_type == "array":
        return _infer_array_schema(values, policy=policy, warnings=warnings, path=path)

    if json_type == "string":
        return _infer_string_schema(values, policy=policy)

    return {"type": json_type}


def _infer_object_schema(
    dict_values: list[dict[str, Any]],
    *,
    policy: SchemaInferencePolicy,
    warnings: list[SchemaInferenceWarning],
    path: str,
    contractual_required: frozenset[str] | None,
) -> dict[str, Any]:
    total = len(dict_values)

    ordered_keys: dict[str, None] = {}
    for document in dict_values:
        for key in document.keys():
            ordered_keys.setdefault(key, None)

    properties: dict[str, Any] = {}
    required: list[str] = []
    for key in ordered_keys:
        values_for_key = [document[key] for document in dict_values if key in document]
        properties[key] = _infer_value_schema(
            values_for_key, policy=policy, warnings=warnings, path=f"{path}.{key}"
        )

        present_in_all_examples = len(values_for_key) == total
        declared_by_contract = contractual_required is not None and key in contractual_required
        if present_in_all_examples or declared_by_contract:
            required.append(key)

    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _infer_array_schema(
    array_values: list[Any],
    *,
    policy: SchemaInferencePolicy,
    warnings: list[SchemaInferenceWarning],
    path: str,
) -> dict[str, Any]:
    items_collected: list[Any] = []
    for array in array_values:
        if isinstance(array, list):
            items_collected.extend(array)

    if not items_collected:
        warnings.append(
            SchemaInferenceWarning(
                code="EMPTY_ARRAY_ITEMS_UNKNOWN",
                message=f"Array vazio em '{path}': tipo dos itens não pôde ser inferido.",
                path=path,
            )
        )
        return {"type": "array"}

    items_schema = _infer_value_schema(
        items_collected, policy=policy, warnings=warnings, path=f"{path}[]"
    )
    return {"type": "array", "items": items_schema}


def _infer_string_schema(values: list[Any], *, policy: SchemaInferencePolicy) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    string_values = [value for value in values if isinstance(value, str)]
    if policy.infer_date_format and string_values and all(
        _ISO_DATE_PATTERN.match(value) for value in string_values
    ):
        schema["format"] = "date"
    return schema
