from dataclasses import dataclass

from api_quality_agent.domain.policies import ensure_non_empty_id


@dataclass(frozen=True)
class CanonicalEndpoint:
    # Chave de pareamento: método HTTP + path canônico (parâmetros de path
    # em qualquer formato de origem já normalizados pro mesmo token
    # "{param}"). Nunca carrega host, protocolo ou query string.
    method: str
    canonical_path: str

    def __post_init__(self) -> None:
        ensure_non_empty_id(self.method, "CanonicalEndpoint.method")
        ensure_non_empty_id(self.canonical_path, "CanonicalEndpoint.canonical_path")
