from dataclasses import dataclass

from api_quality_agent.domain.models.declared_endpoint_contract import DeclaredEndpointContract
from api_quality_agent.domain.policies import ensure_non_empty_id


@dataclass(frozen=True)
class DeclaredContractCatalog:
    # Resultado da leitura de um arquivo de contrato (planilha Excel):
    # todos os contratos de endpoint reconhecidos, com a origem preservada
    # para auditoria/rastreabilidade.
    source_file: str
    contracts: tuple[DeclaredEndpointContract, ...] = ()

    def __post_init__(self) -> None:
        ensure_non_empty_id(self.source_file, "DeclaredContractCatalog.source_file")
