import json
from datetime import datetime
from pathlib import Path
from typing import Any

from api_quality_agent.domain.exceptions import BaselineAlreadyExistsError, ConfigurationError
from api_quality_agent.domain.models import ContractSnapshot, SnapshotKey
from api_quality_agent.domain.policies import sanitize_path_segment

DEFAULT_SNAPSHOT_BASE_PATH = Path("snapshots")


class LocalSnapshotRepository:
    def __init__(self, base_path: Path | None = None) -> None:
        self._base_path = base_path or DEFAULT_SNAPSHOT_BASE_PATH

    def load_baseline(self, key: SnapshotKey) -> ContractSnapshot | None:
        path = self._path_for(key)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError(
                f"Baseline de snapshot corrompido ou ilegível em {path}: {exc}"
            ) from exc
        return _deserialize_snapshot(raw)

    def save_baseline(self, snapshot: ContractSnapshot, *, overwrite: bool = False) -> None:
        path = self._path_for(snapshot.key)
        if path.exists() and not overwrite:
            raise BaselineAlreadyExistsError(
                f"Já existe um baseline para {snapshot.key.method} {snapshot.key.endpoint} "
                f"(workspace={snapshot.key.workspace_id}, collection={snapshot.key.collection_id}). "
                "Atualizar um baseline existente exige overwrite=True explícito."
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(_serialize_snapshot(snapshot), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _path_for(self, key: SnapshotKey) -> Path:
        # A chave (workspace_id/collection_id/method/endpoint) determina
        # inteiramente o caminho: nunca mistura snapshots de Collections
        # diferentes, mesmo que o endpoint tenha o mesmo nome.
        filename = f"{sanitize_path_segment(key.method)}_{sanitize_path_segment(key.endpoint)}.json"
        return (
            self._base_path
            / sanitize_path_segment(key.workspace_id)
            / sanitize_path_segment(key.collection_id)
            / filename
        )


def _serialize_snapshot(snapshot: ContractSnapshot) -> dict[str, Any]:
    return {
        "key": {
            "workspace_id": snapshot.key.workspace_id,
            "collection_id": snapshot.key.collection_id,
            "method": snapshot.key.method,
            "endpoint": snapshot.key.endpoint,
        },
        "captured_at": snapshot.captured_at.isoformat(),
        "status_codes": list(snapshot.status_codes),
        "content_types": list(snapshot.content_types),
        "schema": snapshot.schema,
    }


def _deserialize_snapshot(raw: dict[str, Any]) -> ContractSnapshot:
    key_data = raw["key"]
    return ContractSnapshot(
        key=SnapshotKey(
            workspace_id=key_data["workspace_id"],
            collection_id=key_data["collection_id"],
            method=key_data["method"],
            endpoint=key_data["endpoint"],
        ),
        captured_at=datetime.fromisoformat(raw["captured_at"]),
        status_codes=tuple(raw.get("status_codes") or ()),
        content_types=tuple(raw.get("content_types") or ()),
        schema=raw.get("schema"),
    )
