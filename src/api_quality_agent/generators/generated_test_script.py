from dataclasses import dataclass

from api_quality_agent.generators.generated_test_summary_item import GeneratedTestSummaryItem
from api_quality_agent.generators.generation_warning import GenerationWarning


@dataclass(frozen=True)
class GeneratedTestScript:
    script: str
    summary: tuple[GeneratedTestSummaryItem, ...]
    test_count: int
    warnings: tuple[GenerationWarning, ...]
