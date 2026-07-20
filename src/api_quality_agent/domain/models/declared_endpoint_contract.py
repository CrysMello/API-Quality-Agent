from dataclasses import dataclass

from api_quality_agent.domain.models.declared_request_contract import DeclaredRequestContract
from api_quality_agent.domain.models.declared_response_contract import DeclaredResponseContract
from api_quality_agent.domain.policies import ensure_non_empty_id


@dataclass(frozen=True)
class DeclaredEndpointContract:
    # Contrato declarado de um endpoint, correspondente a uma aba candidata
    # da planilha (identificada por URI + Método). `path` mantém a forma
    # declarada na planilha (com placeholders "{param}"), sem normalização —
    # isso é responsabilidade do futuro ContractEndpointMatcher, não deste
    # modelo.
    method: str
    path: str
    request: DeclaredRequestContract
    response: DeclaredResponseContract
    source_sheet: str
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        ensure_non_empty_id(self.method, "DeclaredEndpointContract.method")
        ensure_non_empty_id(self.path, "DeclaredEndpointContract.path")
        ensure_non_empty_id(self.source_sheet, "DeclaredEndpointContract.source_sheet")
