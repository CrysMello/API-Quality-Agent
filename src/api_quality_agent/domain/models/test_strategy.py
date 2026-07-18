from dataclasses import dataclass

from api_quality_agent.domain.models.assertion_definition import AssertionDefinition
from api_quality_agent.domain.models.negative_case_definition import NegativeCaseDefinition
from api_quality_agent.domain.models.strategy_warning import StrategyWarning
from api_quality_agent.domain.models.variable_extraction import VariableExtraction


@dataclass(frozen=True)
class TestStrategy:
    endpoint_source: str
    assertions: tuple[AssertionDefinition, ...]
    variable_extractions: tuple[VariableExtraction, ...]
    negative_cases: tuple[NegativeCaseDefinition, ...]
    warnings: tuple[StrategyWarning, ...]
