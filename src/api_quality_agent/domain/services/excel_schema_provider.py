from typing import Any

from api_quality_agent.domain.exceptions import InvalidPostmanCollectionError
from api_quality_agent.domain.models import (
    CollectionRequest,
    DeclaredContractCatalog,
    DeclaredSchema,
    MatchStatus,
    SchemaResolution,
)
from api_quality_agent.domain.services.canonical_endpoint_normalizer import (
    CanonicalEndpointNormalizer,
)
from api_quality_agent.domain.services.contract_endpoint_matcher import ContractEndpointMatcher

# R2-05: ExcelSchemaProvider — implementação de SchemaProvider que resolve o
# schema de sucesso (HTTP 200) a partir do contrato declarado na planilha,
# pareando a request real com o catálogo via ContractEndpointMatcher. Sem
# match (NOT_FOUND/AMBIGUOUS) ou sem schema declarado pra esse endpoint,
# devolve schema=None — nunca inventa, nunca cai pra inferência (isso é
# responsabilidade de quem compõe os providers, não deste).


class ExcelSchemaProvider:
    def __init__(
        self,
        catalog: DeclaredContractCatalog,
        matcher: ContractEndpointMatcher,
        normalizer: CanonicalEndpointNormalizer,
    ) -> None:
        self._catalog = catalog
        self._matcher = matcher
        self._normalizer = normalizer

    def resolve(self, request: CollectionRequest) -> SchemaResolution:
        try:
            endpoint = self._normalizer.normalize_collection_request(request.method, request.url)
        except InvalidPostmanCollectionError:
            return SchemaResolution(schema=None)

        match_result = self._matcher.match(endpoint, self._catalog)
        if match_result.status is not MatchStatus.MATCHED or match_result.contract is None:
            return SchemaResolution(schema=None)

        declared_schema = match_result.contract.response.schema
        if declared_schema is None:
            return SchemaResolution(schema=None)

        return SchemaResolution(schema=_to_json_schema(declared_schema))


def _to_json_schema(schema: DeclaredSchema) -> dict[str, Any]:
    result: dict[str, Any] = {"type": schema.type}

    if schema.type == "object":
        properties = {prop.name: _to_json_schema(prop) for prop in schema.properties if prop.name}
        if properties:
            result["properties"] = properties
        required = [prop.name for prop in schema.properties if prop.required and prop.name]
        if required:
            result["required"] = required
    elif schema.type == "array" and schema.items is not None:
        result["items"] = _to_json_schema(schema.items)

    return result
