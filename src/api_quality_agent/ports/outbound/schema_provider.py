from typing import Protocol, runtime_checkable

from api_quality_agent.domain.models import CollectionRequest, SchemaResolution


@runtime_checkable
class SchemaProvider(Protocol):
    # Porta abstrata consultada na resolução do schema de sucesso (HTTP 200)
    # de uma request. Implementações intercambiáveis: schema declarado
    # (planilha de contrato, pareado por endpoint) ou inferido (Examples
    # salvos, comportamento já existente). O AgentOrchestrator ainda não
    # consome esta porta (R2-05) — isso fica pra uma etapa posterior.
    def resolve(self, request: CollectionRequest) -> SchemaResolution: ...
