import re

from api_quality_agent.domain.exceptions import InputError

_UNSAFE_PATH_CHARS = re.compile(r"[^A-Za-z0-9_.-]+")
_MAX_PATH_SEGMENT_LENGTH = 100


def ensure_non_empty_id(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{field_name} deve ser uma string não vazia.")
    return value


def sanitize_path_segment(value: str | None, *, fallback: str = "default") -> str:
    # Usado para compor caminhos de arquivo locais (ex.: backups) a partir de
    # identificadores potencialmente não confiáveis. Nunca deve produzir "..",
    # separadores de diretório ou caracteres incompatíveis com Windows/POSIX.
    if not isinstance(value, str) or not value.strip():
        return fallback

    without_traversal = value.strip().replace("..", "_")
    sanitized = _UNSAFE_PATH_CHARS.sub("_", without_traversal)
    sanitized = sanitized.strip("._")[:_MAX_PATH_SEGMENT_LENGTH]
    return sanitized or fallback
