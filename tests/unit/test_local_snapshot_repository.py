from datetime import datetime, timezone

import pytest

from api_quality_agent.adapters.filesystem import LocalSnapshotRepository
from api_quality_agent.domain.exceptions import BaselineAlreadyExistsError
from api_quality_agent.domain.models import ContractSnapshot, SnapshotKey

CAPTURED_AT = datetime(2026, 7, 19, 12, 0, 0, tzinfo=timezone.utc)

_SCHEMA = {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]}


def _snapshot(
    *,
    workspace_id: str = "ws-1",
    collection_id: str = "c1",
    method: str = "GET",
    endpoint: str = "/pets",
    schema=None,
) -> ContractSnapshot:
    return ContractSnapshot(
        key=SnapshotKey(
            workspace_id=workspace_id,
            collection_id=collection_id,
            method=method,
            endpoint=endpoint,
        ),
        captured_at=CAPTURED_AT,
        status_codes=("200",),
        content_types=("application/json",),
        schema=schema if schema is not None else _SCHEMA,
    )


# --- Primeiro baseline -----------------------------------------------------------------


def test_first_snapshot_creates_baseline(tmp_path):
    repository = LocalSnapshotRepository(tmp_path)
    snapshot = _snapshot()

    assert repository.load_baseline(snapshot.key) is None

    repository.save_baseline(snapshot)

    loaded = repository.load_baseline(snapshot.key)
    assert loaded is not None
    assert loaded.key == snapshot.key
    assert loaded.schema == snapshot.schema
    assert loaded.status_codes == snapshot.status_codes
    assert loaded.content_types == snapshot.content_types
    assert loaded.captured_at == snapshot.captured_at


def test_load_baseline_returns_none_when_absent(tmp_path):
    repository = LocalSnapshotRepository(tmp_path)
    key = SnapshotKey(workspace_id="ws-1", collection_id="c1", method="GET", endpoint="/pets")

    assert repository.load_baseline(key) is None


# --- Atualização explícita do baseline ---------------------------------------------------


def test_saving_over_existing_baseline_without_overwrite_raises(tmp_path):
    repository = LocalSnapshotRepository(tmp_path)
    snapshot = _snapshot()
    repository.save_baseline(snapshot)

    with pytest.raises(BaselineAlreadyExistsError):
        repository.save_baseline(snapshot)


def test_explicit_overwrite_updates_the_baseline(tmp_path):
    repository = LocalSnapshotRepository(tmp_path)
    original = _snapshot(schema=_SCHEMA)
    repository.save_baseline(original)

    updated_schema = {
        "type": "object",
        "properties": {"id": {"type": "integer"}, "email": {"type": "string"}},
        "required": ["id"],
    }
    updated = _snapshot(schema=updated_schema)

    repository.save_baseline(updated, overwrite=True)

    loaded = repository.load_baseline(updated.key)
    assert loaded.schema == updated_schema


# --- Isolamento entre Collections/Workspaces ----------------------------------------------


def test_snapshots_from_different_collections_are_isolated(tmp_path):
    repository = LocalSnapshotRepository(tmp_path)
    snapshot_a = _snapshot(collection_id="ca", schema={"type": "object", "properties": {"a": {"type": "string"}}})
    snapshot_b = _snapshot(collection_id="cb", schema={"type": "object", "properties": {"b": {"type": "string"}}})

    repository.save_baseline(snapshot_a)
    repository.save_baseline(snapshot_b)

    loaded_a = repository.load_baseline(snapshot_a.key)
    loaded_b = repository.load_baseline(snapshot_b.key)

    assert loaded_a.schema != loaded_b.schema
    assert loaded_a.key.collection_id == "ca"
    assert loaded_b.key.collection_id == "cb"


def test_snapshots_from_different_workspaces_are_isolated(tmp_path):
    repository = LocalSnapshotRepository(tmp_path)
    snapshot_a = _snapshot(workspace_id="ws-1", collection_id="c1")
    snapshot_b = _snapshot(workspace_id="ws-2", collection_id="c1")

    repository.save_baseline(snapshot_a)
    repository.save_baseline(snapshot_b)

    assert repository.load_baseline(snapshot_a.key) is not None
    assert repository.load_baseline(snapshot_b.key) is not None


def test_different_endpoints_in_same_collection_do_not_collide(tmp_path):
    repository = LocalSnapshotRepository(tmp_path)
    snapshot_pets = _snapshot(endpoint="/pets", method="GET")
    snapshot_owners = _snapshot(endpoint="/owners", method="GET")

    repository.save_baseline(snapshot_pets)
    repository.save_baseline(snapshot_owners)

    assert repository.load_baseline(snapshot_pets.key) is not None
    assert repository.load_baseline(snapshot_owners.key) is not None


def test_different_methods_on_same_endpoint_do_not_collide(tmp_path):
    repository = LocalSnapshotRepository(tmp_path)
    snapshot_get = _snapshot(method="GET", endpoint="/pets")
    snapshot_post = _snapshot(method="POST", endpoint="/pets")

    repository.save_baseline(snapshot_get)
    repository.save_baseline(snapshot_post)

    assert repository.load_baseline(snapshot_get.key) is not None
    assert repository.load_baseline(snapshot_post.key) is not None


def test_path_traversal_in_identifiers_is_neutralized(tmp_path):
    repository = LocalSnapshotRepository(tmp_path)
    snapshot = _snapshot(
        workspace_id="../../etc",
        collection_id="../../passwd",
        method="GET",
        endpoint="/../../secret",
    )

    repository.save_baseline(snapshot)

    for path in tmp_path.rglob("*.json"):
        assert tmp_path.resolve() in path.resolve().parents
