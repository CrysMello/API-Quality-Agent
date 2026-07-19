from typing import Protocol, runtime_checkable

from api_quality_agent.domain.models import ExecutionResultLocation


@runtime_checkable
class ExecutionResultRepository(Protocol):
    def save(self, *, content: str) -> ExecutionResultLocation: ...
