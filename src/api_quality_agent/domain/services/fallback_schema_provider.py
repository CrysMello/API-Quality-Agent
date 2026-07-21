from api_quality_agent.domain.models import CollectionRequest, SchemaResolution
from api_quality_agent.ports.outbound import SchemaProvider

# R2-07: compõe dois SchemaProvider — tenta o primário (schema declarado);
# se ele não resolver nada (endpoint sem contrato, NOT_FOUND, AMBIGUOUS),
# cai pro secundário (inferência), preservando o comportamento atual pra
# endpoints fora da planilha. Política padrão descrita no SAD: contrato
# declarado tem prioridade, inferência é o fallback.


class FallbackSchemaProvider:
    def __init__(self, primary: SchemaProvider, fallback: SchemaProvider) -> None:
        self._primary = primary
        self._fallback = fallback

    def resolve(self, request: CollectionRequest) -> SchemaResolution:
        resolution = self._primary.resolve(request)
        if resolution.schema is not None:
            return resolution
        return self._fallback.resolve(request)
