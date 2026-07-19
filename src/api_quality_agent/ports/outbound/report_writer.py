from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class ReportWriter(Protocol):
    def write(self, *, path: Path, content: str) -> None: ...
