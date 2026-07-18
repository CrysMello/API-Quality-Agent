import json
from pathlib import Path
from typing import Any

from api_quality_agent.domain.exceptions import ConfigurationError
from api_quality_agent.domain.models import ActiveSelection

DEFAULT_SELECTION_FILE_PATH = Path.home() / ".api-quality-agent" / "selection.json"


class FileSelectionRepository:
    def __init__(self, file_path: Path | None = None) -> None:
        self._file_path = file_path or DEFAULT_SELECTION_FILE_PATH

    def load(self) -> ActiveSelection:
        if not self._file_path.exists():
            return ActiveSelection()

        try:
            raw_text = self._file_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigurationError(
                f"Não foi possível ler o arquivo de seleção: {self._file_path}"
            ) from exc

        try:
            raw_data: Any = json.loads(raw_text) if raw_text.strip() else {}
        except json.JSONDecodeError as exc:
            raise ConfigurationError(
                f"Arquivo de seleção corrompido (JSON inválido): {self._file_path}"
            ) from exc

        if not isinstance(raw_data, dict):
            raise ConfigurationError(f"Arquivo de seleção inválido: {self._file_path}")

        return ActiveSelection(
            workspace_id=_clean_id(raw_data.get("workspace_id")),
            collection_id=_clean_id(raw_data.get("collection_id")),
        )

    def save(self, selection: ActiveSelection) -> None:
        # Somente IDs são persistidos: nunca nomes, nunca a API Key.
        payload = {
            "workspace_id": selection.workspace_id,
            "collection_id": selection.collection_id,
        }
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        self._file_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _clean_id(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
