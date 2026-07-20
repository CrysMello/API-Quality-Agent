from __future__ import annotations

from dataclasses import dataclass

from api_quality_agent.domain.exceptions import InputError
from api_quality_agent.domain.policies import ensure_non_empty_id

_VALID_TYPES = frozenset({"string", "number", "integer", "boolean", "object", "array"})


@dataclass(frozen=True)
class DeclaredSchema:
    # Representa um schema declarado (não inferido): um nó da árvore
    # reconstruída a partir da coluna Sequencial da planilha de contrato.
    # `name` é None para a raiz e para o schema de item de um array (que não
    # tem nome próprio); nos demais casos representa o nome do campo.
    type: str
    required: bool
    name: str | None = None
    properties: tuple["DeclaredSchema", ...] = ()
    items: "DeclaredSchema | None" = None

    def __post_init__(self) -> None:
        if self.name is not None:
            ensure_non_empty_id(self.name, "DeclaredSchema.name")
        if self.type not in _VALID_TYPES:
            raise InputError(f"DeclaredSchema.type inválido: {self.type!r}")
        if self.type != "object" and self.properties:
            raise InputError(
                "DeclaredSchema.properties só é válido quando type == 'object'."
            )
        if self.type != "array" and self.items is not None:
            raise InputError("DeclaredSchema.items só é válido quando type == 'array'.")
