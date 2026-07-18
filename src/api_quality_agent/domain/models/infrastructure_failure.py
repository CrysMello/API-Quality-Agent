from dataclasses import dataclass

from api_quality_agent.domain.models.infrastructure_failure_type import InfrastructureFailureType


@dataclass(frozen=True)
class InfrastructureFailure:
    failure_type: InfrastructureFailureType
    message: str
