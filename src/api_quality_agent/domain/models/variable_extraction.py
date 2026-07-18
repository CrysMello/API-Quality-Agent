from dataclasses import dataclass

from api_quality_agent.domain.models.variable_scope import VariableScope


@dataclass(frozen=True)
class VariableExtraction:
    variable_name: str
    source: str
    json_path: str
    scope: VariableScope
    origin: str
