import json

from api_quality_agent.domain.models import (
    CanonicalEndpoint,
    ContractMatchResult,
    DeclaredEndpointContract,
    DeclaredRequestContract,
    DeclaredResponseContract,
    MatchStatus,
)
from api_quality_agent.reporting import (
    build_contract_match_report,
    render_contract_match_report_html,
    render_contract_match_report_json,
    render_contract_match_report_summary,
    serialize_contract_match_report,
)


def _contract(method, path, source_sheet="Planilha1"):
    return DeclaredEndpointContract(
        method=method,
        path=path,
        request=DeclaredRequestContract(),
        response=DeclaredResponseContract(),
        source_sheet=source_sheet,
    )


def _endpoint(method, path):
    return CanonicalEndpoint(method=method, canonical_path=path)


def _sample_results():
    matched_contract = _contract("GET", "/v2/pet/{petId}", source_sheet="Planilha1")
    ambiguous_a = _contract("GET", "/v2/order/{id}", source_sheet="Planilha2")
    ambiguous_b = _contract("GET", "/v2/order/{orderId}", source_sheet="Planilha3")
    return (
        ContractMatchResult(
            status=MatchStatus.MATCHED,
            endpoint=_endpoint("GET", "/v2/pet/{param}"),
            contract=matched_contract,
        ),
        ContractMatchResult(
            status=MatchStatus.NOT_FOUND, endpoint=_endpoint("DELETE", "/v2/pet/{param}")
        ),
        ContractMatchResult(
            status=MatchStatus.AMBIGUOUS,
            endpoint=_endpoint("GET", "/v2/order/{param}"),
            candidates=(ambiguous_a, ambiguous_b),
        ),
    )


def test_build_report_computes_summary_counts():
    report = build_contract_match_report("contrato.xlsx", _sample_results())

    assert report.schema_version == "1.0"
    assert report.source_file == "contrato.xlsx"
    assert report.summary.total == 3
    assert report.summary.matched == 1
    assert report.summary.not_found == 1
    assert report.summary.ambiguous == 1
    assert len(report.entries) == 3


def test_matched_entry_carries_sheet_and_declared_path():
    report = build_contract_match_report("contrato.xlsx", _sample_results())

    matched_entry = next(entry for entry in report.entries if entry.status is MatchStatus.MATCHED)
    assert matched_entry.sheet == "Planilha1"
    assert matched_entry.declared_path == "/v2/pet/{petId}"
    assert matched_entry.candidate_sheets == ()


def test_ambiguous_entry_carries_candidate_sheets_never_a_single_choice():
    report = build_contract_match_report("contrato.xlsx", _sample_results())

    ambiguous_entry = next(entry for entry in report.entries if entry.status is MatchStatus.AMBIGUOUS)
    assert set(ambiguous_entry.candidate_sheets) == {"Planilha2", "Planilha3"}
    assert ambiguous_entry.sheet is None
    assert ambiguous_entry.declared_path is None


def test_not_found_entry_carries_no_extra_data():
    report = build_contract_match_report("contrato.xlsx", _sample_results())

    not_found_entry = next(entry for entry in report.entries if entry.status is MatchStatus.NOT_FOUND)
    assert not_found_entry.sheet is None
    assert not_found_entry.candidate_sheets == ()


def test_serialize_matches_the_documented_json_shape():
    report = build_contract_match_report("contrato.xlsx", _sample_results())

    payload = serialize_contract_match_report(report)

    assert payload["schema_version"] == "1.0"
    assert payload["source"] == "contrato.xlsx"
    assert payload["summary"] == {"contracts": 3, "matched": 1, "not_found": 1, "ambiguous": 1}
    matched_payload = next(m for m in payload["matches"] if m["status"] == "MATCHED")
    assert matched_payload["sheet"] == "Planilha1"
    assert matched_payload["declared_path"] == "/v2/pet/{petId}"
    ambiguous_payload = next(m for m in payload["matches"] if m["status"] == "AMBIGUOUS")
    assert set(ambiguous_payload["candidates"]) == {"Planilha2", "Planilha3"}
    not_found_payload = next(m for m in payload["matches"] if m["status"] == "NOT_FOUND")
    assert "sheet" not in not_found_payload
    assert "candidates" not in not_found_payload


def test_render_json_is_valid_and_round_trips():
    report = build_contract_match_report("contrato.xlsx", _sample_results())

    text = render_contract_match_report_json(report)
    parsed = json.loads(text)

    assert parsed == serialize_contract_match_report(report)


def test_render_summary_contains_the_counts():
    report = build_contract_match_report("contrato.xlsx", _sample_results())

    summary = render_contract_match_report_summary(report)

    assert "contrato.xlsx" in summary
    assert "Endpoints declarados: 3" in summary
    assert "Correspondências: 1" in summary
    assert "Não encontrados: 1" in summary
    assert "Ambíguos: 1" in summary


def test_render_html_contains_status_labels_and_escapes_user_data():
    dangerous_contract = _contract("GET", "/v2/<script>", source_sheet="<script>alert(1)</script>")
    results = (
        ContractMatchResult(
            status=MatchStatus.MATCHED,
            endpoint=_endpoint("GET", "/v2/{param}"),
            contract=dangerous_contract,
        ),
    )
    report = build_contract_match_report("contrato.xlsx", results)

    html = render_contract_match_report_html(report)

    assert "MATCHED" in html
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_render_html_handles_an_empty_report():
    report = build_contract_match_report("contrato.xlsx", ())

    html = render_contract_match_report_html(report)

    assert "Nenhum endpoint declarado" in html
