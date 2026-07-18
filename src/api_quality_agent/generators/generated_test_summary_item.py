from dataclasses import dataclass

from api_quality_agent.generators.test_category import TestCategory


@dataclass(frozen=True)
class GeneratedTestSummaryItem:
    test_id: str
    title: str
    description: str
    category: TestCategory
    source: str | None
