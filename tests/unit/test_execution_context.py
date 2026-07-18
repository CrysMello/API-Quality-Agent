import dataclasses
from datetime import datetime, timezone

import pytest

from api_quality_agent.domain.exceptions import InputError
from api_quality_agent.domain.models import ExecutionContext, ExecutionMode

FIXED_INSTANT = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)


def _fixed_clock() -> datetime:
    return FIXED_INSTANT


def _make_context(**overrides):
    params = {
        "mode": ExecutionMode.OFFLINE,
        "source": "json",
        "id_factory": lambda: "exec-fixed-id",
        "clock": _fixed_clock,
    }
    params.update(overrides)
    return ExecutionContext.create(**params)


def test_create_uses_injected_id_factory_and_clock():
    context = _make_context()
    assert context.execution_id == "exec-fixed-id"
    assert context.started_at == FIXED_INSTANT


def test_create_accepts_string_mode():
    context = _make_context(mode="online")
    assert context.mode == ExecutionMode.ONLINE


def test_rejects_naive_started_at():
    with pytest.raises(InputError):
        ExecutionContext(
            execution_id="exec-1",
            started_at=datetime(2026, 7, 17, 12, 0),
            mode=ExecutionMode.OFFLINE,
            source="json",
        )


def test_rejects_empty_execution_id():
    with pytest.raises(InputError):
        ExecutionContext(
            execution_id="",
            started_at=FIXED_INSTANT,
            mode=ExecutionMode.OFFLINE,
            source="json",
        )


def test_rejects_empty_source():
    with pytest.raises(InputError):
        ExecutionContext(
            execution_id="exec-1",
            started_at=FIXED_INSTANT,
            mode=ExecutionMode.OFFLINE,
            source="   ",
        )


def test_rejects_invalid_mode():
    with pytest.raises(InputError):
        ExecutionContext(
            execution_id="exec-1",
            started_at=FIXED_INSTANT,
            mode="invalid-mode",
            source="json",
        )


def test_rejects_empty_optional_identifiers():
    with pytest.raises(InputError):
        ExecutionContext(
            execution_id="exec-1",
            started_at=FIXED_INSTANT,
            mode=ExecutionMode.OFFLINE,
            source="json",
            workspace_id="",
        )


def test_warnings_default_to_independent_empty_lists():
    context_a = _make_context(id_factory=lambda: "a")
    context_b = _make_context(id_factory=lambda: "b")
    context_a.add_warning("aviso")
    assert context_a.warnings == ["aviso"]
    assert context_b.warnings == []


def test_add_warning_rejects_empty_message():
    context = _make_context()
    with pytest.raises(InputError):
        context.add_warning("")


def test_add_artifact_reference():
    context = _make_context()
    context.add_artifact_reference("schemas/output.json")
    assert context.artifact_references == ["schemas/output.json"]


def test_to_dict_serializes_expected_fields():
    context = _make_context(
        mode=ExecutionMode.ONLINE,
        source="postman",
        workspace_id="ws-1",
        workspace_name="Workspace 1",
        collection_id="col-1",
        collection_name="Collection 1",
    )
    context.add_warning("aviso")

    data = context.to_dict()

    assert data == {
        "execution_id": "exec-fixed-id",
        "started_at": FIXED_INSTANT.isoformat(),
        "mode": "online",
        "source": "postman",
        "workspace_id": "ws-1",
        "workspace_name": "Workspace 1",
        "collection_id": "col-1",
        "collection_name": "Collection 1",
        "warnings": ["aviso"],
        "artifact_references": [],
    }


def test_to_dict_never_contains_credential_like_keys():
    context = _make_context()
    data = context.to_dict()
    forbidden = {"api_key", "apikey", "token", "secret", "password", "credential"}
    assert forbidden.isdisjoint({key.lower() for key in data.keys()})


def test_execution_context_has_no_credential_attribute():
    context = _make_context()
    field_names = {f.name for f in dataclasses.fields(context)}
    forbidden = {"api_key", "apikey", "token", "secret", "password", "credential"}
    assert forbidden.isdisjoint(field_names)
