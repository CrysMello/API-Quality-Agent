from collections.abc import Callable
from datetime import datetime, timezone

from api_quality_agent import __version__
from api_quality_agent.application.orchestration import CollectionGenerationResult
from api_quality_agent.application.orchestration.endpoint_generation_outcome import (
    EndpointGenerationOutcome,
)
from api_quality_agent.application.use_cases import CollectionUpdateResult
from api_quality_agent.domain.models import (
    ArtifactLocation,
    ExecutionResult,
    GeneratedArtifact,
    SelectionOrigin,
)
from api_quality_agent.ports.outbound import ArtifactRepository
from api_quality_agent.reporting.report import (
    Report,
    ReportDiffEntry,
    ReportDiffSection,
    ReportEndpointSummary,
    ReportExecutionSection,
    ReportInfrastructureFailure,
    ReportTestFailure,
    ReportUpdateSection,
)
from api_quality_agent.reporting.report_html_renderer import render_report_html
from api_quality_agent.reporting.report_serializer import render_report_json

REPORT_CATEGORY = "reports"
REPORT_JSON_FILENAME = "report.json"
REPORT_HTML_FILENAME = "report.html"


class ReportEngine:
    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def generate(
        self,
        generation_result: CollectionGenerationResult,
        *,
        selection_origin: SelectionOrigin = SelectionOrigin.ACTIVE,
        update_result: CollectionUpdateResult | None = None,
        update_denied_reason: str | None = None,
        execution_result: ExecutionResult | None = None,
        agent_version: str = __version__,
    ) -> Report:
        execution_context = generation_result.execution_context
        generated_at = self._clock()
        duration_seconds = max(
            (generated_at - execution_context.started_at).total_seconds(), 0.0
        )

        return Report(
            execution_id=execution_context.execution_id,
            generated_at=generated_at,
            duration_seconds=duration_seconds,
            mode=execution_context.mode.value,
            source=execution_context.source,
            workspace_id=execution_context.workspace_id,
            workspace_name=execution_context.workspace_name,
            collection_id=execution_context.collection_id,
            collection_name=execution_context.collection_name,
            selection_origin=selection_origin.value,
            endpoints=tuple(
                _build_endpoint_summary(outcome)
                for outcome in generation_result.endpoint_outcomes
            ),
            analysis_warnings=tuple(
                warning.message for warning in generation_result.analysis_warnings
            ),
            execution_warnings=tuple(execution_context.warnings),
            diff=_build_diff_section(generation_result),
            update=_build_update_section(
                update_result=update_result, update_denied_reason=update_denied_reason
            ),
            execution=_build_execution_section(execution_result),
            artifacts=tuple(
                location.path for location in generation_result.artifact_locations
            ),
            agent_version=agent_version,
        )

    def save(
        self,
        report: Report,
        artifact_repository: ArtifactRepository,
        *,
        workspace_id: str,
        collection_id: str,
        execution_id: str,
        include_html: bool = False,
    ) -> tuple[ArtifactLocation, ...]:
        # execution_id sempre faz parte do caminho (via ArtifactRepository),
        # garantindo que relatórios de execuções diferentes nunca colidam nem
        # se sobrescrevem silenciosamente.
        locations = [
            artifact_repository.save(
                workspace_id=workspace_id,
                collection_id=collection_id,
                execution_id=execution_id,
                artifact=GeneratedArtifact(
                    category=REPORT_CATEGORY,
                    relative_path=REPORT_JSON_FILENAME,
                    content=render_report_json(report),
                ),
            )
        ]
        if include_html:
            locations.append(
                artifact_repository.save(
                    workspace_id=workspace_id,
                    collection_id=collection_id,
                    execution_id=execution_id,
                    artifact=GeneratedArtifact(
                        category=REPORT_CATEGORY,
                        relative_path=REPORT_HTML_FILENAME,
                        content=render_report_html(report),
                    ),
                )
            )
        return tuple(locations)


def _build_endpoint_summary(outcome: EndpointGenerationOutcome) -> ReportEndpointSummary:
    test_count = outcome.generated_script.test_count if outcome.generated_script else 0
    return ReportEndpointSummary(
        source=outcome.endpoint_source,
        succeeded=outcome.error is None,
        test_count=test_count,
        schema_warning_count=len(outcome.schema_warnings),
        strategy_warning_count=len(outcome.strategy_warnings),
        error=outcome.error,
    )


def _build_diff_section(generation_result: CollectionGenerationResult) -> ReportDiffSection:
    diff = generation_result.diff
    return ReportDiffSection(
        entries=tuple(
            ReportDiffEntry(
                change_type=entry.change_type.value,
                category=entry.category.value,
                target=entry.target,
                risk=entry.risk.value,
                description=entry.description,
            )
            for entry in diff.entries
        ),
        has_changes=diff.has_changes,
        has_removals=diff.has_removals,
        has_high_risk_changes=diff.has_high_risk_changes,
    )


def _build_update_section(
    *,
    update_result: CollectionUpdateResult | None,
    update_denied_reason: str | None,
) -> ReportUpdateSection:
    if update_result is not None:
        return ReportUpdateSection(
            attempted=True,
            approved=True,
            updated=update_result.updated,
            dry_run=update_result.dry_run,
            denial_reason=None,
            backup_created=update_result.backup_created,
            document_hash=update_result.document_hash,
            status_code=update_result.status_code,
        )
    if update_denied_reason is not None:
        return ReportUpdateSection(
            attempted=True,
            approved=False,
            updated=False,
            dry_run=None,
            denial_reason=update_denied_reason,
            backup_created=None,
            document_hash=None,
            status_code=None,
        )
    return ReportUpdateSection(
        attempted=False,
        approved=None,
        updated=None,
        dry_run=None,
        denial_reason=None,
        backup_created=None,
        document_hash=None,
        status_code=None,
    )


def _build_execution_section(
    execution_result: ExecutionResult | None,
) -> ReportExecutionSection:
    if execution_result is None:
        return ReportExecutionSection(
            executed=False,
            success=None,
            exit_code=None,
            duration_seconds=None,
            total_requests=None,
            total_assertions=None,
            failed_assertions=None,
            test_failures=(),
            infrastructure_failure=None,
        )

    infrastructure_failure = None
    if execution_result.infrastructure_failure is not None:
        infrastructure_failure = ReportInfrastructureFailure(
            failure_type=execution_result.infrastructure_failure.failure_type.value,
            message=execution_result.infrastructure_failure.message,
        )

    return ReportExecutionSection(
        executed=True,
        success=execution_result.success,
        exit_code=execution_result.exit_code,
        duration_seconds=execution_result.duration_seconds,
        total_requests=execution_result.total_requests,
        total_assertions=execution_result.total_assertions,
        failed_assertions=execution_result.failed_assertions,
        test_failures=tuple(
            ReportTestFailure(
                request_name=failure.request_name,
                test_name=failure.test_name,
                error_message=failure.error_message,
            )
            for failure in execution_result.test_failures
        ),
        infrastructure_failure=infrastructure_failure,
    )
