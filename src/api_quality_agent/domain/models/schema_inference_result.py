from dataclasses import dataclass
from typing import Any

from api_quality_agent.domain.models.schema_inference_warning import SchemaInferenceWarning


@dataclass(frozen=True)
class SchemaInferenceResult:
    schema: dict[str, Any]
    warnings: tuple[SchemaInferenceWarning, ...]
