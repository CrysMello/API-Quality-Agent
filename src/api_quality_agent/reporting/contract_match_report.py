from dataclasses import dataclass

from api_quality_agent.domain.models import ContractMatchResult, ContractValidationIssue, MatchStatus

# R2-08: relatório de correspondência entre o contrato declarado (planilha)
# e as requests reais da Collection — igual ao adendo v1.1 seção 3 previa:
# schema_version obrigatório, um único conjunto de entradas capaz de
# representar MATCHED/NOT_FOUND/AMBIGUOUS (candidatos nunca escolhidos
# automaticamente), sem inventar dado que o matcher não produziu.
#
# R2-09A: correlação com os diagnósticos do ExcelContractValidator, sempre
# por source_sheet (chave já existente nos dois lados — uma aba produz no
# máximo um contrato hoje, então sheet já é uma correlação determinística,
# sem precisar de contract_id nem de faixa de linhas). NOT_FOUND nunca
# recebe correlação: não há nenhuma aba/candidato referenciado nessas
# entradas, então não há evidência determinística a associar — associar por
# proximidade textual seria a heurística que este projeto proíbe.

_SCHEMA_VERSION = "1.1"


@dataclass(frozen=True)
class CandidateValidationIssues:
    sheet: str
    issues: tuple[ContractValidationIssue, ...]


@dataclass(frozen=True)
class ContractMatchEntry:
    method: str
    canonical_path: str
    status: MatchStatus
    sheet: str | None = None
    declared_path: str | None = None
    # Preenchido só quando status == AMBIGUOUS.
    candidate_sheets: tuple[str, ...] = ()
    # Diagnósticos de validação da aba `sheet` — só quando status == MATCHED
    # e há issues correlacionadas.
    validation_issues: tuple[ContractValidationIssue, ...] = ()
    # Diagnósticos de validação por candidato — só quando status == AMBIGUOUS
    # e algum candidato tem issues correlacionadas.
    candidate_validation_issues: tuple[CandidateValidationIssues, ...] = ()


@dataclass(frozen=True)
class ContractMatchSummary:
    total: int
    matched: int
    not_found: int
    ambiguous: int


@dataclass(frozen=True)
class ContractMatchReport:
    schema_version: str
    source_file: str
    summary: ContractMatchSummary
    entries: tuple[ContractMatchEntry, ...]
    # Todos os diagnósticos de validação, sem filtro — inclui os de abas
    # sem contrato utilizável (nunca aparecem em `entries`) e os já
    # correlacionados em alguma entrada MATCHED/AMBIGUOUS.
    validation_issues: tuple[ContractValidationIssue, ...] = ()


def build_contract_match_report(
    source_file: str,
    results: tuple[ContractMatchResult, ...],
    validation_issues: tuple[ContractValidationIssue, ...] = (),
) -> ContractMatchReport:
    issues_by_sheet = _group_issues_by_sheet(validation_issues)
    entries = tuple(_to_entry(result, issues_by_sheet) for result in results)
    summary = ContractMatchSummary(
        total=len(entries),
        matched=sum(1 for entry in entries if entry.status is MatchStatus.MATCHED),
        not_found=sum(1 for entry in entries if entry.status is MatchStatus.NOT_FOUND),
        ambiguous=sum(1 for entry in entries if entry.status is MatchStatus.AMBIGUOUS),
    )
    return ContractMatchReport(
        schema_version=_SCHEMA_VERSION,
        source_file=source_file,
        summary=summary,
        entries=entries,
        validation_issues=validation_issues,
    )


def _group_issues_by_sheet(
    issues: tuple[ContractValidationIssue, ...],
) -> dict[str, tuple[ContractValidationIssue, ...]]:
    grouped: dict[str, list[ContractValidationIssue]] = {}
    for issue in issues:
        grouped.setdefault(issue.sheet, []).append(issue)
    return {sheet: tuple(sheet_issues) for sheet, sheet_issues in grouped.items()}


def _to_entry(
    result: ContractMatchResult,
    issues_by_sheet: dict[str, tuple[ContractValidationIssue, ...]],
) -> ContractMatchEntry:
    method = result.endpoint.method
    canonical_path = result.endpoint.canonical_path
    status = result.status

    if status is MatchStatus.MATCHED and result.contract is not None:
        return ContractMatchEntry(
            method=method,
            canonical_path=canonical_path,
            status=status,
            sheet=result.contract.source_sheet,
            declared_path=result.contract.path,
            validation_issues=issues_by_sheet.get(result.contract.source_sheet, ()),
        )
    if status is MatchStatus.AMBIGUOUS:
        candidate_sheets = tuple(candidate.source_sheet for candidate in result.candidates)
        candidate_validation_issues = tuple(
            CandidateValidationIssues(sheet=sheet, issues=issues_by_sheet[sheet])
            for sheet in candidate_sheets
            if sheet in issues_by_sheet
        )
        return ContractMatchEntry(
            method=method,
            canonical_path=canonical_path,
            status=status,
            candidate_sheets=candidate_sheets,
            candidate_validation_issues=candidate_validation_issues,
        )
    # NOT_FOUND: nunca correlacionado — nenhuma aba é referenciada por esta
    # entrada, então não há chave determinística para buscar issues.
    return ContractMatchEntry(method=method, canonical_path=canonical_path, status=status)
