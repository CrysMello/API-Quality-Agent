from dataclasses import dataclass
from typing import Any

from api_quality_agent.domain.models.schema_inference_warning import SchemaInferenceWarning


@dataclass(frozen=True)
class SchemaResolution:
    # Resultado de um SchemaProvider: o schema de sucesso resolvido pra uma
    # request (dict de JSON Schema, ou None quando não há schema disponível
    # por essa fonte) e os warnings associados. `warnings` reaproveita o
    # mesmo tipo já usado pela inferência — providers que não inferem nada
    # (ex.: schema declarado) simplesmente devolvem uma tupla vazia.
    schema: dict[str, Any] | None
    warnings: tuple[SchemaInferenceWarning, ...] = ()
