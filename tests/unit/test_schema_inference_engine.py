import pytest

from api_quality_agent.domain.exceptions import InputError
from api_quality_agent.domain.models import SchemaInferencePolicy
from api_quality_agent.domain.services import SchemaInferenceEngine


def test_infers_all_supported_scalar_and_container_types():
    examples = [
        {
            "text": "hello",
            "count": 42,
            "price": 9.99,
            "active": True,
            "notes": None,
            "address": {"city": "São Paulo", "zip": "01000-000"},
            "tags": ["a", "b"],
        }
    ]

    result = SchemaInferenceEngine().infer(examples)
    properties = result.schema["properties"]

    assert properties["text"] == {"type": "string"}
    assert properties["count"] == {"type": "integer"}
    assert properties["price"] == {"type": "number"}
    assert properties["active"] == {"type": "boolean"}
    assert properties["notes"] == {"type": "null"}
    assert properties["address"]["type"] == "object"
    assert properties["address"]["properties"]["city"] == {"type": "string"}
    assert properties["tags"] == {"type": "array", "items": {"type": "string"}}
    assert result.schema["type"] == "object"
    assert "$schema" in result.schema


def test_root_array_is_inferred():
    result = SchemaInferenceEngine().infer([[1, 2, 3]])

    assert result.schema["type"] == "array"
    assert result.schema["items"] == {"type": "integer"}


def test_nested_array_of_objects():
    examples = [{"items": [{"id": 1}, {"id": 2}]}]

    result = SchemaInferenceEngine().infer(examples)

    item_schema = result.schema["properties"]["items"]["items"]
    assert item_schema["type"] == "object"
    assert item_schema["properties"]["id"] == {"type": "integer"}
    assert item_schema["required"] == ["id"]


# --- Array vazio ---------------------------------------------------------------


def test_empty_array_does_not_infer_items_type():
    result = SchemaInferenceEngine().infer([[]])

    assert result.schema["type"] == "array"
    assert "items" not in result.schema
    assert any(w.code == "EMPTY_ARRAY_ITEMS_UNKNOWN" for w in result.warnings)


def test_empty_array_field_does_not_infer_items_type():
    examples = [{"tags": []}]

    result = SchemaInferenceEngine().infer(examples)

    assert result.schema["properties"]["tags"] == {"type": "array"}


def test_array_with_some_empty_and_some_populated_examples_infers_from_populated():
    examples = [{"tags": []}, {"tags": ["a"]}]

    result = SchemaInferenceEngine().infer(examples)

    assert result.schema["properties"]["tags"] == {"type": "array", "items": {"type": "string"}}


# --- Campos opcionais ------------------------------------------------------------


def test_field_present_in_only_some_examples_is_not_required():
    examples = [{"id": 1, "nickname": "Rex"}, {"id": 2}]

    result = SchemaInferenceEngine().infer(examples)

    assert "nickname" not in result.schema["required"]
    assert result.schema["properties"]["nickname"] == {"type": "string"}


# --- Campos nulos ------------------------------------------------------------------


def test_field_that_is_sometimes_null_becomes_nullable_union_without_inconsistency_warning():
    examples = [{"tag": "dog"}, {"tag": None}]

    result = SchemaInferenceEngine().infer(examples)

    assert result.schema["properties"]["tag"] == {"type": ["null", "string"]}
    assert not any(w.code == "INCONSISTENT_TYPE" for w in result.warnings)


def test_field_always_null_infers_null_type():
    examples = [{"tag": None}, {"tag": None}]

    result = SchemaInferenceEngine().infer(examples)

    assert result.schema["properties"]["tag"] == {"type": "null"}


# --- Exemplos inconsistentes ----------------------------------------------------


def test_inconsistent_types_generate_union_and_warning():
    examples = [{"value": "texto"}, {"value": 42}]

    result = SchemaInferenceEngine().infer(examples)

    assert result.schema["properties"]["value"] == {"type": ["integer", "string"]}
    assert any(w.code == "INCONSISTENT_TYPE" for w in result.warnings)


# --- Required por múltiplos exemplos ---------------------------------------------


def test_field_present_in_all_examples_is_required():
    examples = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}, {"id": 3, "name": "c"}]

    result = SchemaInferenceEngine().infer(examples)

    assert set(result.schema["required"]) == {"id", "name"}


# --- Required declarado por contrato ---------------------------------------------


def test_contractual_required_field_is_marked_required_even_if_absent_from_some_examples():
    examples = [{"a": 1}, {"a": 2, "b": 3}]

    result = SchemaInferenceEngine().infer(examples, contractual_required=frozenset({"b"}))

    assert "b" in result.schema["required"]


def test_contractual_required_does_not_apply_to_nested_objects():
    examples = [{"address": {"city": "SP"}}, {"address": {}}]

    result = SchemaInferenceEngine().infer(examples, contractual_required=frozenset({"city"}))

    nested_required = result.schema["properties"]["address"].get("required", [])
    assert "city" not in nested_required


# --- String com aparência de data -------------------------------------------------


def test_date_like_string_remains_plain_string_by_default():
    examples = [{"created_at": "2026-07-17"}]

    result = SchemaInferenceEngine().infer(examples)

    assert result.schema["properties"]["created_at"] == {"type": "string"}


def test_date_like_string_gets_format_only_when_policy_enables_it():
    examples = [{"created_at": "2026-07-17"}]
    policy = SchemaInferencePolicy(infer_date_format=True)

    result = SchemaInferenceEngine().infer(examples, policy=policy)

    assert result.schema["properties"]["created_at"] == {"type": "string", "format": "date"}


def test_non_date_string_is_not_affected_by_date_policy():
    examples = [{"name": "Rex"}]
    policy = SchemaInferencePolicy(infer_date_format=True)

    result = SchemaInferenceEngine().infer(examples, policy=policy)

    assert result.schema["properties"]["name"] == {"type": "string"}


# --- Ordem determinística -----------------------------------------------------


def test_property_order_matches_first_appearance_across_examples():
    examples = [{"c": 1, "a": 2}, {"a": 3, "b": 4}]

    result = SchemaInferenceEngine().infer(examples)

    assert list(result.schema["properties"].keys()) == ["c", "a", "b"]


def test_property_order_is_stable_across_multiple_runs():
    examples = [{"z": 1, "y": 2, "x": 3}]
    engine = SchemaInferenceEngine()

    first = list(engine.infer(examples).schema["properties"].keys())
    second = list(engine.infer(examples).schema["properties"].keys())

    assert first == second == ["z", "y", "x"]


# --- Idempotência --------------------------------------------------------------


def test_same_input_produces_the_same_schema_every_time():
    examples = [
        {"id": 1, "name": "Rex", "tags": ["a", "b"]},
        {"id": 2, "name": "Mimi"},
    ]
    engine = SchemaInferenceEngine()

    first = engine.infer(examples)
    second = engine.infer(examples)

    assert first.schema == second.schema
    assert first.warnings == second.warnings


# --- Regras de segurança / anti-invenção -----------------------------------------


def test_no_format_is_inferred_from_field_name_alone():
    examples = [{"email": "user@example.com", "cpf": "12345678900", "id_uuid": "abc-123"}]

    result = SchemaInferenceEngine().infer(examples)

    assert result.schema["properties"]["email"] == {"type": "string"}
    assert result.schema["properties"]["cpf"] == {"type": "string"}
    assert result.schema["properties"]["id_uuid"] == {"type": "string"}


def test_example_values_are_never_embedded_as_const_or_enum():
    examples = [{"token": "super-secret-value"}]

    result = SchemaInferenceEngine().infer(examples)

    schema_text = str(result.schema)
    assert "const" not in result.schema["properties"]["token"]
    assert "enum" not in result.schema["properties"]["token"]
    assert "super-secret-value" not in schema_text


def test_raises_input_error_when_no_examples_are_provided():
    with pytest.raises(InputError):
        SchemaInferenceEngine().infer([])
