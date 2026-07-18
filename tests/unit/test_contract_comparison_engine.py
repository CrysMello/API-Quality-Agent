from datetime import datetime, timezone

import pytest

from api_quality_agent.domain.exceptions import InputError
from api_quality_agent.domain.models import (
    ChangeSeverity,
    ContractChangeType,
    ContractSnapshot,
    SnapshotKey,
)
from api_quality_agent.domain.services import ContractComparisonEngine

CAPTURED_AT = datetime(2026, 7, 19, 12, 0, 0, tzinfo=timezone.utc)


def _snapshot(
    schema,
    *,
    workspace_id: str = "ws-1",
    collection_id: str = "c1",
    method: str = "GET",
    endpoint: str = "/pets",
    status_codes: tuple[str, ...] = ("200",),
    content_types: tuple[str, ...] = ("application/json",),
) -> ContractSnapshot:
    return ContractSnapshot(
        key=SnapshotKey(
            workspace_id=workspace_id,
            collection_id=collection_id,
            method=method,
            endpoint=endpoint,
        ),
        captured_at=CAPTURED_AT,
        status_codes=status_codes,
        content_types=content_types,
        schema=schema,
    )


_BASE_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "name": {"type": "string"},
    },
    "required": ["id", "name"],
}


def _engine() -> ContractComparisonEngine:
    return ContractComparisonEngine()


# --- Sem alteração ---------------------------------------------------------------------


def test_identical_schemas_produce_no_changes():
    baseline = _snapshot(_BASE_SCHEMA)
    current = _snapshot(dict(_BASE_SCHEMA))

    changes = _engine().compare(baseline, current)

    assert changes == ()


# --- Adição ------------------------------------------------------------------------------


def test_added_field_is_detected_with_low_severity():
    baseline = _snapshot(_BASE_SCHEMA)
    current_schema = {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "name": {"type": "string"},
            "email": {"type": "string"},
        },
        "required": ["id", "name"],
    }
    current = _snapshot(current_schema)

    changes = _engine().compare(baseline, current)

    assert len(changes) == 1
    assert changes[0].change_type == ContractChangeType.FIELD_ADDED
    assert changes[0].severity == ChangeSeverity.LOW
    assert changes[0].field_path == "$.email"


# --- Remoção -----------------------------------------------------------------------------


def test_removed_field_is_detected_with_high_severity():
    baseline = _snapshot(_BASE_SCHEMA)
    current_schema = {
        "type": "object",
        "properties": {"id": {"type": "integer"}},
        "required": ["id"],
    }
    current = _snapshot(current_schema)

    changes = _engine().compare(baseline, current)

    assert len(changes) == 1
    assert changes[0].change_type == ContractChangeType.FIELD_REMOVED
    assert changes[0].severity == ChangeSeverity.HIGH
    assert changes[0].field_path == "$.name"


# --- Tipo --------------------------------------------------------------------------------


def test_type_change_is_detected_with_high_severity():
    baseline = _snapshot(_BASE_SCHEMA)
    current_schema = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
        },
        "required": ["id", "name"],
    }
    current = _snapshot(current_schema)

    changes = _engine().compare(baseline, current)

    assert len(changes) == 1
    assert changes[0].change_type == ContractChangeType.TYPE_CHANGED
    assert changes[0].severity == ChangeSeverity.HIGH
    assert changes[0].field_path == "$.id"


# --- Required ----------------------------------------------------------------------------


def test_required_change_is_detected_with_medium_severity():
    baseline = _snapshot(_BASE_SCHEMA)
    current_schema = {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "name": {"type": "string"},
        },
        "required": ["id"],
    }
    current = _snapshot(current_schema)

    changes = _engine().compare(baseline, current)

    assert len(changes) == 1
    assert changes[0].change_type == ContractChangeType.REQUIRED_CHANGED
    assert changes[0].severity == ChangeSeverity.MEDIUM
    assert changes[0].field_path == "$.name"


# --- Enum --------------------------------------------------------------------------------


def test_enum_change_is_detected_with_medium_severity():
    baseline_schema = {
        "type": "object",
        "properties": {"status": {"type": "string", "enum": ["active", "inactive"]}},
    }
    current_schema = {
        "type": "object",
        "properties": {"status": {"type": "string", "enum": ["active", "inactive", "pending"]}},
    }
    baseline = _snapshot(baseline_schema)
    current = _snapshot(current_schema)

    changes = _engine().compare(baseline, current)

    assert len(changes) == 1
    assert changes[0].change_type == ContractChangeType.ENUM_CHANGED
    assert changes[0].severity == ChangeSeverity.MEDIUM
    assert changes[0].field_path == "$.status"


def test_enum_with_same_values_in_different_order_produces_no_change():
    baseline_schema = {
        "type": "object",
        "properties": {"status": {"type": "string", "enum": ["active", "inactive"]}},
    }
    current_schema = {
        "type": "object",
        "properties": {"status": {"type": "string", "enum": ["inactive", "active"]}},
    }

    changes = _engine().compare(_snapshot(baseline_schema), _snapshot(current_schema))

    assert changes == ()


# --- Ordem diferente -----------------------------------------------------------------------


def test_property_order_difference_produces_no_changes():
    baseline_schema = {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "name": {"type": "string"},
        },
        "required": ["id", "name"],
    }
    current_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "id": {"type": "integer"},
        },
        "required": ["name", "id"],
    }

    changes = _engine().compare(_snapshot(baseline_schema), _snapshot(current_schema))

    assert changes == ()


# --- Status code / content type -------------------------------------------------------------


def test_status_code_change_is_detected():
    baseline = _snapshot(_BASE_SCHEMA, status_codes=("200",))
    current = _snapshot(_BASE_SCHEMA, status_codes=("200", "404"))

    changes = _engine().compare(baseline, current)

    assert len(changes) == 1
    assert changes[0].change_type == ContractChangeType.STATUS_CODE_CHANGED
    assert changes[0].severity == ChangeSeverity.MEDIUM


def test_status_codes_in_different_order_produce_no_change():
    baseline = _snapshot(_BASE_SCHEMA, status_codes=("200", "404"))
    current = _snapshot(_BASE_SCHEMA, status_codes=("404", "200"))

    assert _engine().compare(baseline, current) == ()


def test_content_type_change_is_detected():
    baseline = _snapshot(_BASE_SCHEMA, content_types=("application/json",))
    current = _snapshot(_BASE_SCHEMA, content_types=("application/xml",))

    changes = _engine().compare(baseline, current)

    assert len(changes) == 1
    assert changes[0].change_type == ContractChangeType.CONTENT_TYPE_CHANGED
    assert changes[0].severity == ChangeSeverity.MEDIUM


# --- Collections diferentes -----------------------------------------------------------------


def test_comparing_different_collections_raises_input_error():
    baseline = _snapshot(_BASE_SCHEMA, collection_id="c1")
    current = _snapshot(_BASE_SCHEMA, collection_id="c2")

    with pytest.raises(InputError):
        _engine().compare(baseline, current)


def test_comparing_different_workspaces_raises_input_error():
    baseline = _snapshot(_BASE_SCHEMA, workspace_id="ws-1")
    current = _snapshot(_BASE_SCHEMA, workspace_id="ws-2")

    with pytest.raises(InputError):
        _engine().compare(baseline, current)


def test_comparing_different_endpoints_raises_input_error():
    baseline = _snapshot(_BASE_SCHEMA, endpoint="/pets")
    current = _snapshot(_BASE_SCHEMA, endpoint="/owners")

    with pytest.raises(InputError):
        _engine().compare(baseline, current)


# --- Rastreamento aninhado (arrays) e determinismo -------------------------------------------


def test_type_change_inside_array_items_is_detected():
    baseline_schema = {"type": "array", "items": {"type": "integer"}}
    current_schema = {"type": "array", "items": {"type": "string"}}

    changes = _engine().compare(_snapshot(baseline_schema), _snapshot(current_schema))

    assert len(changes) == 1
    assert changes[0].change_type == ContractChangeType.TYPE_CHANGED
    assert changes[0].field_path == "$[]"


def test_comparison_is_deterministic_across_repeated_calls():
    current_schema = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "email": {"type": "string"},
        },
        "required": ["id"],
    }
    baseline = _snapshot(_BASE_SCHEMA)
    current = _snapshot(current_schema)
    engine = _engine()

    first = engine.compare(baseline, current)
    second = engine.compare(baseline, current)

    assert first == second
