from pathlib import Path
from typing import Protocol, runtime_checkable

from api_quality_agent.domain.models import ExecutionResultRecord


@runtime_checkable
class ExecutionResultReader(Protocol):
    def find_latest(self) -> Path | None: ...

    def read(self, *, path: Path) -> ExecutionResultRecord: ...
