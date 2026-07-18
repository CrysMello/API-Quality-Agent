from dataclasses import dataclass
from typing import Any

from api_quality_agent.domain.models.assertion_type import AssertionType


@dataclass(frozen=True)
class AssertionDefinition:
    assertion_type: AssertionType
    description: str
    expected_value: Any
    origin: str
    enabled: bool = True
