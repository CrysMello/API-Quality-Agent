import json
from typing import Any

from api_quality_agent.domain.models import ContractValidationIssue
from api_quality_agent.reporting.contract_match_report import (
    CandidateValidationIssues,
    ContractMatchEntry,
    ContractMatchReport,
)


def serialize_contract_match_report(report: ContractMatchReport) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": report.schema_version,
        "source": report.source_file,
        "summary": {
            "contracts": report.summary.total,
            "matched": report.summary.matched,
            "not_found": report.summary.not_found,
            "ambiguous": report.summary.ambiguous,
        },
        "matches": [_serialize_entry(entry) for entry in report.entries],
    }
    if report.validation_issues:
        result["validation_issues"] = [_serialize_issue(issue) for issue in report.validation_issues]
    return result


def _serialize_entry(entry: ContractMatchEntry) -> dict[str, Any]:
    result: dict[str, Any] = {
        "method": entry.method,
        "path": entry.canonical_path,
        "status": entry.status.value,
    }
    if entry.sheet is not None:
        result["sheet"] = entry.sheet
    if entry.declared_path is not None:
        result["declared_path"] = entry.declared_path
    if entry.candidate_sheets:
        result["candidates"] = list(entry.candidate_sheets)
    if entry.validation_issues:
        result["validation_issues"] = [_serialize_issue(issue) for issue in entry.validation_issues]
    if entry.candidate_validation_issues:
        result["candidate_validation_issues"] = [
            _serialize_candidate_issues(candidate) for candidate in entry.candidate_validation_issues
        ]
    return result


def _serialize_issue(issue: ContractValidationIssue) -> dict[str, Any]:
    result: dict[str, Any] = {
        "severity": issue.severity,
        "sheet": issue.sheet,
        "message": issue.message,
    }
    if issue.section is not None:
        result["section"] = issue.section
    if issue.row_number is not None:
        result["row"] = issue.row_number
    if issue.field is not None:
        result["field"] = issue.field
    return result


def _serialize_candidate_issues(candidate: CandidateValidationIssues) -> dict[str, Any]:
    return {
        "sheet": candidate.sheet,
        "issues": [_serialize_issue(issue) for issue in candidate.issues],
    }


def render_contract_match_report_json(report: ContractMatchReport) -> str:
    return json.dumps(
        serialize_contract_match_report(report), indent=2, ensure_ascii=False, sort_keys=True
    )
