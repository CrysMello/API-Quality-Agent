from dataclasses import dataclass

from api_quality_agent.domain.models.declared_parameter import DeclaredParameter
from api_quality_agent.domain.models.declared_schema import DeclaredSchema


@dataclass(frozen=True)
class DeclaredRequestContract:
    # Contrato declarado do lado da requisição: Header, Path Param, Query
    # Param e Body — cada seção pode estar vazia, como já previsto no SAD.
    headers: tuple[DeclaredParameter, ...] = ()
    path_parameters: tuple[DeclaredParameter, ...] = ()
    query_parameters: tuple[DeclaredParameter, ...] = ()
    body_schema: DeclaredSchema | None = None
