from typing import Protocol, runtime_checkable

from api_quality_agent.domain.models import ExecutionResult

DEFAULT_RUN_TIMEOUT_SECONDS = 300.0


@runtime_checkable
class CollectionRunner(Protocol):
    def run(
        self,
        *,
        collection_path: str,
        environment_path: str | None = None,
        timeout_seconds: float = DEFAULT_RUN_TIMEOUT_SECONDS,
    ) -> ExecutionResult: ...
