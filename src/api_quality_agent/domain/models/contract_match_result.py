from dataclasses import dataclass

from api_quality_agent.domain.models.canonical_endpoint import CanonicalEndpoint
from api_quality_agent.domain.models.declared_endpoint_contract import DeclaredEndpointContract
from api_quality_agent.domain.models.match_status import MatchStatus


@dataclass(frozen=True)
class ContractMatchResult:
    status: MatchStatus
    endpoint: CanonicalEndpoint
    contract: DeclaredEndpointContract | None = None
    # Preenchido apenas quando status == AMBIGUOUS — nunca escolhido
    # automaticamente (sem fuzzy matching, sem desempate silencioso).
    candidates: tuple[DeclaredEndpointContract, ...] = ()
