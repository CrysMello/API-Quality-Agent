from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from api_quality_agent.domain.models import ExecutionResultLocation

DEFAULT_EXECUTION_RESULTS_BASE_PATH = Path("artifacts")

# Precisão de microssegundos evita colisão de nome entre execuções de `run`
# sucessivas e rápidas (o mesmo raciocínio já usado em LocalBackupRepository).
_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S%f"
_RESULT_FILENAME = "result.json"


class JsonExecutionResultRepository:
    def __init__(
        self,
        base_path: Path | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._base_path = base_path or DEFAULT_EXECUTION_RESULTS_BASE_PATH
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def save(self, *, content: str) -> ExecutionResultLocation:
        timestamp = self._clock().strftime(_TIMESTAMP_FORMAT)
        target_dir = self._base_path / f"run_{timestamp}"
        target_dir.mkdir(parents=True, exist_ok=True)

        target_path = target_dir / _RESULT_FILENAME
        target_path.write_text(content, encoding="utf-8")

        return ExecutionResultLocation(path=str(target_path))
