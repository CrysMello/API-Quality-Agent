from dataclasses import dataclass

from api_quality_agent.domain.models.declared_schema import DeclaredSchema
from api_quality_agent.domain.models.parameter_location import ParameterLocation
from api_quality_agent.domain.policies import ensure_non_empty_id


@dataclass(frozen=True)
class DeclaredParameter:
    # Um parâmetro declarado de Header, Path Param ou Query Param — as
    # seções da planilha de contrato que não fazem parte do corpo.
    name: str
    location: ParameterLocation
    required: bool
    schema: DeclaredSchema

    def __post_init__(self) -> None:
        ensure_non_empty_id(self.name, "DeclaredParameter.name")
