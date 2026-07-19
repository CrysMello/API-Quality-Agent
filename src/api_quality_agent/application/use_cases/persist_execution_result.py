import json
from datetime import datetime
from typing import Any

from api_quality_agent.domain.models import ExecutionResult, ExecutionResultLocation
from api_quality_agent.ports.outbound import ExecutionResultRepository


class PersistExecutionResultUseCase:
    def __init__(self, execution_result_repository: ExecutionResultRepository) -> None:
        self._execution_result_repository = execution_result_repository

    def execute(
        self,
        result: ExecutionResult,
        *,
        collection_id: str,
        collection_name: str,
        started_at: datetime,
        finished_at: datetime,
    ) -> ExecutionResultLocation:
        content = json.dumps(
            _serialize(
                result,
                collection_id=collection_id,
                collection_name=collection_name,
                started_at=started_at,
                finished_at=finished_at,
            ),
            indent=2,
            ensure_ascii=False,
        )
        return self._execution_result_repository.save(content=content)


def _serialize(
    result: ExecutionResult,
    *,
    collection_id: str,
    collection_name: str,
    started_at: datetime,
    finished_at: datetime,
) -> dict[str, Any]:
    # Serialização explícita e estruturada: nunca stdout/stderr brutos, nunca
    # a Collection completa — só os campos já expostos pelo domínio, usados
    # como entrada oficial de um futuro `api-quality-agent report`.
    infrastructure_failure = result.infrastructure_failure
    return {
        "execution": {
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_seconds": result.duration_seconds,
        },
        "collection": {
            "id": collection_id,
            "name": collection_name,
        },
        "summary": {
            "requests": result.total_requests,
            "assertions": result.total_assertions,
            "passed": result.total_assertions - result.failed_assertions,
            "failed": result.failed_assertions,
        },
        "success": result.success,
        "infrastructure_failure": (
            {
                "type": infrastructure_failure.failure_type.value,
                "message": infrastructure_failure.message,
            }
            if infrastructure_failure is not None
            else None
        ),
    }
