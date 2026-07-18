import json
from typing import Any

from api_quality_agent.reporting.report import Report

# Conjunto de chaves de topo estável e explícito: qualquer alteração aqui é
# uma mudança de contrato do relatório e deve ser deliberada.
REPORT_SCHEMA_TOP_LEVEL_KEYS = frozenset(
    {
        "execution_id",
        "generated_at",
        "duration_seconds",
        "mode",
        "source",
        "workspace_id",
        "workspace_name",
        "collection_id",
        "collection_name",
        "selection_origin",
        "endpoints",
        "analysis_warnings",
        "execution_warnings",
        "diff",
        "update",
        "execution",
        "artifacts",
        "agent_version",
    }
)


def serialize_report(report: Report) -> dict[str, Any]:
    return {
        "execution_id": report.execution_id,
        "generated_at": report.generated_at.isoformat(),
        "duration_seconds": report.duration_seconds,
        "mode": report.mode,
        "source": report.source,
        "workspace_id": report.workspace_id,
        "workspace_name": report.workspace_name,
        "collection_id": report.collection_id,
        "collection_name": report.collection_name,
        "selection_origin": report.selection_origin,
        "endpoints": [
            {
                "source": endpoint.source,
                "succeeded": endpoint.succeeded,
                "test_count": endpoint.test_count,
                "schema_warning_count": endpoint.schema_warning_count,
                "strategy_warning_count": endpoint.strategy_warning_count,
                "error": endpoint.error,
            }
            for endpoint in report.endpoints
        ],
        "analysis_warnings": list(report.analysis_warnings),
        "execution_warnings": list(report.execution_warnings),
        "diff": {
            "entries": [
                {
                    "change_type": entry.change_type,
                    "category": entry.category,
                    "target": entry.target,
                    "risk": entry.risk,
                    "description": entry.description,
                }
                for entry in report.diff.entries
            ],
            "has_changes": report.diff.has_changes,
            "has_removals": report.diff.has_removals,
            "has_high_risk_changes": report.diff.has_high_risk_changes,
        },
        "update": {
            "attempted": report.update.attempted,
            "approved": report.update.approved,
            "updated": report.update.updated,
            "dry_run": report.update.dry_run,
            "denial_reason": report.update.denial_reason,
            "backup_created": report.update.backup_created,
            "document_hash": report.update.document_hash,
            "status_code": report.update.status_code,
        },
        "execution": {
            "executed": report.execution.executed,
            "success": report.execution.success,
            "exit_code": report.execution.exit_code,
            "duration_seconds": report.execution.duration_seconds,
            "total_requests": report.execution.total_requests,
            "total_assertions": report.execution.total_assertions,
            "failed_assertions": report.execution.failed_assertions,
            "test_failures": [
                {
                    "request_name": failure.request_name,
                    "test_name": failure.test_name,
                    "error_message": failure.error_message,
                }
                for failure in report.execution.test_failures
            ],
            "infrastructure_failure": (
                {
                    "failure_type": report.execution.infrastructure_failure.failure_type,
                    "message": report.execution.infrastructure_failure.message,
                }
                if report.execution.infrastructure_failure is not None
                else None
            ),
        },
        "artifacts": list(report.artifacts),
        "agent_version": report.agent_version,
    }


def render_report_json(report: Report) -> str:
    return json.dumps(serialize_report(report), indent=2, ensure_ascii=False, sort_keys=True)
