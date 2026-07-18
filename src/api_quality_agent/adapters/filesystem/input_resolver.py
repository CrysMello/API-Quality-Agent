import sys
from pathlib import Path
from typing import TextIO

from api_quality_agent.domain.exceptions import (
    EmptyInputError,
    InputEncodingError,
    InputFileNotFoundError,
    InputSizeLimitExceededError,
    UnsupportedInputExtensionError,
)
from api_quality_agent.domain.models import InputOrigin, ResolvedInput

DEFAULT_MAX_INPUT_SIZE_BYTES = 10 * 1024 * 1024
DEFAULT_SUPPORTED_EXTENSIONS = frozenset({".json"})
DEFAULT_CONTENT_TYPE = "json"


class InputResolver:
    def __init__(
        self,
        *,
        max_size_bytes: int = DEFAULT_MAX_INPUT_SIZE_BYTES,
        supported_extensions: frozenset[str] = DEFAULT_SUPPORTED_EXTENSIONS,
    ) -> None:
        self._max_size_bytes = max_size_bytes
        self._supported_extensions = supported_extensions

    def resolve_from_file(self, path: str | Path) -> ResolvedInput:
        file_path = Path(path)

        if not file_path.is_file():
            raise InputFileNotFoundError(f"Arquivo não encontrado: {file_path}")

        extension = file_path.suffix.lower()
        if extension not in self._supported_extensions:
            supported = ", ".join(sorted(self._supported_extensions))
            raise UnsupportedInputExtensionError(
                f"Extensão não suportada '{extension}' em {file_path}. Suportadas: {supported}"
            )

        size = file_path.stat().st_size
        if size == 0:
            raise EmptyInputError(f"Arquivo vazio: {file_path}")
        self._ensure_within_size_limit(size, source_name=str(file_path))

        content = self._decode(file_path.read_bytes(), source_name=str(file_path))

        return ResolvedInput(
            origin=InputOrigin.FILE,
            content_type=DEFAULT_CONTENT_TYPE,
            name=str(file_path),
            content=content,
        )

    def resolve_from_stdin(
        self, stream: TextIO | None = None, *, name: str = "<stdin>"
    ) -> ResolvedInput:
        source = stream if stream is not None else sys.stdin
        content = source.read()

        if len(content.encode("utf-8")) == 0:
            raise EmptyInputError("Entrada padrão (stdin) vazia.")
        self._ensure_within_size_limit(len(content.encode("utf-8")), source_name=name)

        return ResolvedInput(
            origin=InputOrigin.STDIN,
            content_type=DEFAULT_CONTENT_TYPE,
            name=name,
            content=content,
        )

    def resolve_from_content(
        self,
        content: str,
        *,
        name: str = "<inline>",
        content_type: str = DEFAULT_CONTENT_TYPE,
    ) -> ResolvedInput:
        if len(content.encode("utf-8")) == 0:
            raise EmptyInputError(f"Conteúdo informado está vazio: {name}")
        self._ensure_within_size_limit(len(content.encode("utf-8")), source_name=name)

        return ResolvedInput(
            origin=InputOrigin.INLINE,
            content_type=content_type,
            name=name,
            content=content,
        )

    def _ensure_within_size_limit(self, size_in_bytes: int, *, source_name: str) -> None:
        if size_in_bytes > self._max_size_bytes:
            raise InputSizeLimitExceededError(
                f"Entrada excede o limite de tamanho "
                f"({size_in_bytes} > {self._max_size_bytes} bytes): {source_name}"
            )

    @staticmethod
    def _decode(raw_bytes: bytes, *, source_name: str) -> str:
        try:
            return raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise InputEncodingError(
                f"Encoding inválido (esperado UTF-8) em {source_name}: {exc}"
            ) from exc
