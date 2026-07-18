import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from api_quality_agent.domain.exceptions import ConfigurationError

_UNSET = object()


class ConfigurationProvider:
    def __init__(
        self,
        *,
        overrides: Mapping[str, Any] | None = None,
        environment: Mapping[str, str] | None = None,
        file_values: Mapping[str, Any] | None = None,
        config_file_path: str | Path | None = None,
        defaults: Mapping[str, Any] | None = None,
    ) -> None:
        self._overrides: dict[str, Any] = dict(overrides or {})
        self._environment: dict[str, Any] = (
            dict(environment) if environment is not None else dict(os.environ)
        )
        self._file_values: dict[str, Any] = (
            dict(file_values) if file_values is not None else self._load_file(config_file_path)
        )
        self._defaults: dict[str, Any] = dict(defaults or {})

    @staticmethod
    def _load_file(path: str | Path | None) -> dict[str, Any]:
        if path is None:
            return {}
        file_path = Path(path)
        if not file_path.exists():
            return {}
        try:
            content = file_path.read_text(encoding="utf-8")
            data = json.loads(content)
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError(
                f"Não foi possível carregar o arquivo de configuração: {file_path}"
            ) from exc
        if not isinstance(data, dict):
            raise ConfigurationError(f"Arquivo de configuração inválido: {file_path}")
        return data

    def get(self, key: str, default: Any = _UNSET) -> Any:
        for source in (self._overrides, self._environment, self._file_values, self._defaults):
            if key in source and source[key] is not None:
                return source[key]
        if default is not _UNSET:
            return default
        raise ConfigurationError(f"Configuração ausente: {key}")

    def require(self, key: str) -> Any:
        value = self.get(key)
        if isinstance(value, str) and not value.strip():
            raise ConfigurationError(f"Configuração inválida (vazia): {key}")
        return value
