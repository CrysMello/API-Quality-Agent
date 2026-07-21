import json

from api_quality_agent.domain.models import (
    CanonicalEndpoint,
    ContractMatchResult,
    ContractValidationIssue,
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

    assert report.schema_version == "1.1"
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

    assert payload["schema_version"] == "1.1"
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


# R2-09A: correlação com os diagnósticos do ExcelContractValidator, sempre
# por source_sheet (chave já existente nos dois lados, determinística —
# sem contract_id, sem faixa de linhas, sem fuzzy matching).


def _issue(sheet, *, severity="error", section=None, row_number=None, field=None, message="erro"):
    return ContractValidationIssue(
        severity=severity, sheet=sheet, section=section, row_number=row_number, field=field, message=message
    )


def test_matched_entry_carries_validation_issues_from_its_own_sheet():
    issues = (_issue("Planilha1", field="Formato", row_number=30, message="Tipo desconhecido"),)

    report = build_contract_match_report("contrato.xlsx", _sample_results(), validation_issues=issues)

    matched_entry = next(entry for entry in report.entries if entry.status is MatchStatus.MATCHED)
    assert matched_entry.validation_issues == issues


def test_matched_entry_without_issues_on_its_sheet_has_no_validation_issues():
    issues = (_issue("Planilha2", message="não pertence à aba do MATCHED"),)

    report = build_contract_match_report("contrato.xlsx", _sample_results(), validation_issues=issues)

    matched_entry = next(entry for entry in report.entries if entry.status is MatchStatus.MATCHED)
    assert matched_entry.validation_issues == ()


def test_matched_entry_preserves_multiple_issues_on_the_same_sheet():
    issues = (
        _issue("Planilha1", field="Formato", message="erro 1"),
        _issue("Planilha1", field="Sequencial", message="erro 2"),
    )

    report = build_contract_match_report("contrato.xlsx", _sample_results(), validation_issues=issues)

    matched_entry = next(entry for entry in report.entries if entry.status is MatchStatus.MATCHED)
    assert len(matched_entry.validation_issues) == 2


def test_ambiguous_entry_carries_candidate_validation_issues_separately_per_candidate():
    issues = (
        _issue("Planilha2", field="Formato", message="erro no candidato A"),
        _issue("Planilha3", field="Sequencial", message="erro no candidato B"),
    )

    report = build_contract_match_report("contrato.xlsx", _sample_results(), validation_issues=issues)

    ambiguous_entry = next(entry for entry in report.entries if entry.status is MatchStatus.AMBIGUOUS)
    by_sheet = {c.sheet: c.issues for c in ambiguous_entry.candidate_validation_issues}
    assert by_sheet["Planilha2"][0].message == "erro no candidato A"
    assert by_sheet["Planilha3"][0].message == "erro no candidato B"


def test_not_found_entry_never_receives_validation_issues_even_with_similar_sheet_names():
    # Issue numa aba com path parecido ("outra-coisa" perto de "/v2/pet") não
    # deve ser associada ao NOT_FOUND — não há evidência determinística,
    # NOT_FOUND não referencia nenhuma aba.
    issues = (_issue("PlanilhaParecidaComPet", message="pode parecer relacionado, mas não é"),)

    report = build_contract_match_report("contrato.xlsx", _sample_results(), validation_issues=issues)

    not_found_entry = next(entry for entry in report.entries if entry.status is MatchStatus.NOT_FOUND)
    assert not_found_entry.validation_issues == ()
    assert not_found_entry.candidate_validation_issues == ()


def test_issue_on_a_sheet_without_a_usable_contract_stays_only_in_the_general_list():
    # Aba sem contrato no catálogo (nunca aparece em matches[]) — a issue
    # não deve ser forçada para dentro de nenhuma entrada.
    issues = (_issue("PlanilhaSemContrato", message="método/URI ausentes"),)

    report = build_contract_match_report("contrato.xlsx", _sample_results(), validation_issues=issues)

    assert report.validation_issues == issues
    assert all(entry.validation_issues == () for entry in report.entries)
    assert all(entry.candidate_validation_issues == () for entry in report.entries)


def test_report_validation_issues_contains_every_issue_unfiltered():
    issues = (
        _issue("Planilha1", message="correlacionada"),
        _issue("PlanilhaSemContrato", message="sem contrato"),
    )

    report = build_contract_match_report("contrato.xlsx", _sample_results(), validation_issues=issues)

    assert report.validation_issues == issues


def test_serialize_includes_validation_issues_only_when_present():
    matched_issues = (_issue("Planilha1", section="body", row_number=30, field="Formato", message="erro"),)
    report = build_contract_match_report(
        "contrato.xlsx", _sample_results(), validation_issues=matched_issues
    )

    payload = serialize_contract_match_report(report)

    matched_payload = next(m for m in payload["matches"] if m["status"] == "MATCHED")
    assert matched_payload["validation_issues"] == [
        {"severity": "error", "sheet": "Planilha1", "section": "body", "row": 30, "field": "Formato", "message": "erro"}
    ]
    not_found_payload = next(m for m in payload["matches"] if m["status"] == "NOT_FOUND")
    assert "validation_issues" not in not_found_payload
    assert payload["validation_issues"] == matched_payload["validation_issues"]


def test_serialize_omits_validation_issues_key_when_there_are_none():
    report = build_contract_match_report("contrato.xlsx", _sample_results())

    payload = serialize_contract_match_report(report)

    assert "validation_issues" not in payload
    for match in payload["matches"]:
        assert "validation_issues" not in match
        assert "candidate_validation_issues" not in match


def test_serialize_ambiguous_candidate_validation_issues_structured_per_candidate():
    issues = (_issue("Planilha2", message="erro no candidato A"),)
    report = build_contract_match_report("contrato.xlsx", _sample_results(), validation_issues=issues)

    payload = serialize_contract_match_report(report)

    ambiguous_payload = next(m for m in payload["matches"] if m["status"] == "AMBIGUOUS")
    assert ambiguous_payload["candidate_validation_issues"] == [
        {"sheet": "Planilha2", "issues": [{"severity": "error", "sheet": "Planilha2", "message": "erro no candidato A"}]}
    ]


def test_render_html_shows_validation_issue_counts_and_general_section():
    issues = (_issue("Planilha1", field="Formato", row_number=30, message="Tipo desconhecido"),)
    report = build_contract_match_report("contrato.xlsx", _sample_results(), validation_issues=issues)

    html = render_contract_match_report_html(report)

    assert "Diagnósticos de validação" in html
    assert "Tipo desconhecido" in html


def test_render_html_omits_validation_section_when_there_are_no_issues():
    report = build_contract_match_report("contrato.xlsx", _sample_results())

    html = render_contract_match_report_html(report)

    assert "Diagnósticos de validação" not in html
