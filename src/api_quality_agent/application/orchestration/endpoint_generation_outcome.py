from dataclasses import dataclass

from api_quality_agent.domain.models import SchemaInferenceWarning, StrategyWarning
from api_quality_agent.generators import GeneratedTestScript


@dataclass(frozen=True)
class EndpointGenerationOutcome:
    endpoint_source: str
    generated_script: GeneratedTestScript | None
    # Texto completo do script "test" após o merge do bloco gerenciado —
    # inclui qualquer código manual preexistente, preservado ao redor do
    # bloco. É o que efetivamente iria para o campo Tests do Postman.
    merged_script: str | None
    schema_warnings: tuple[SchemaInferenceWarning, ...]
    strategy_warnings: tuple[StrategyWarning, ...]
    error: str | None
