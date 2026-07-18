from typing import Protocol, runtime_checkable

from api_quality_agent.domain.models import ActiveSelection


@runtime_checkable
class SelectionRepository(Protocol):
    def load(self) -> ActiveSelection: ...

    def save(self, selection: ActiveSelection) -> None: ...
