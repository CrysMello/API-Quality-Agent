from api_quality_agent.domain.models import (
    CanonicalEndpoint,
    ContractMatchResult,
    DeclaredContractCatalog,
    DeclaredEndpointContract,
    MatchStatus,
)
from api_quality_agent.domain.services.canonical_endpoint_normalizer import (
    CanonicalEndpointNormalizer,
)

# R2-04: ContractEndpointMatcher — localiza o contrato declarado
# correspondente a um endpoint já canonizado, usando só método + path
# canônico. Não interpreta URLs (recebe um CanonicalEndpoint já pronto),
# não resolve variável de infraestrutura, não analisa query string, não
# acessa arquivo Excel — só compara chaves já normalizadas. Determinístico:
# nunca escolhe automaticamente entre candidatos ambíguos.


class ContractEndpointMatcher:
    def __init__(self, normalizer: CanonicalEndpointNormalizer) -> None:
        self._normalizer = normalizer

    def match(self, endpoint: CanonicalEndpoint, catalog: DeclaredContractCatalog) -> ContractMatchResult:
        grouped = self._group_by_canonical_endpoint(catalog)
        return self._match_one(endpoint, grouped)

    def match_all(
        self, endpoints: tuple[CanonicalEndpoint, ...], catalog: DeclaredContractCatalog
    ) -> tuple[ContractMatchResult, ...]:
        grouped = self._group_by_canonical_endpoint(catalog)
        return tuple(self._match_one(endpoint, grouped) for endpoint in endpoints)

    def _group_by_canonical_endpoint(
        self, catalog: DeclaredContractCatalog
    ) -> dict[CanonicalEndpoint, list[DeclaredEndpointContract]]:
        grouped: dict[CanonicalEndpoint, list[DeclaredEndpointContract]] = {}
        for contract in catalog.contracts:
            key = self._normalizer.normalize_declared_endpoint(contract.method, contract.path)
            grouped.setdefault(key, []).append(contract)
        return grouped

    @staticmethod
    def _match_one(
        endpoint: CanonicalEndpoint,
        grouped: dict[CanonicalEndpoint, list[DeclaredEndpointContract]],
    ) -> ContractMatchResult:
        candidates = grouped.get(endpoint, [])
        if not candidates:
            return ContractMatchResult(status=MatchStatus.NOT_FOUND, endpoint=endpoint)
        if len(candidates) > 1:
            return ContractMatchResult(
                status=MatchStatus.AMBIGUOUS, endpoint=endpoint, candidates=tuple(candidates)
            )
        return ContractMatchResult(status=MatchStatus.MATCHED, endpoint=endpoint, contract=candidates[0])
