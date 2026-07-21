import json
from typing import Any

from api_quality_agent.reporting.contract_match_report import ContractMatchEntry, ContractMatchReport


def serialize_contract_match_report(report: ContractMatchReport) -> dict[str, Any]:
    return {
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
    return result


def render_contract_match_report_json(report: ContractMatchReport) -> str:
    return json.dumps(
        serialize_contract_match_report(report), indent=2, ensure_ascii=False, sort_keys=True
    )
