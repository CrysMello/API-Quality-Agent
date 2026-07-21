from dataclasses import dataclass

from api_quality_agent.domain.models import ContractMatchResult, MatchStatus

# R2-08: relatório de correspondência entre o contrato declarado (planilha)
# e as requests reais da Collection — igual ao adendo v1.1 seção 3 previa:
# schema_version obrigatório, um único conjunto de entradas capaz de
# representar MATCHED/NOT_FOUND/AMBIGUOUS (candidatos nunca escolhidos
# automaticamente), sem inventar dado que o matcher não produziu.
#
# INVALID_CONTRACT (do ExcelContractValidator, R2-03) não é correlacionado
# aqui ainda — os diagnósticos de validação são por linha/campo, os do
# matcher são por endpoint; essa junção fica pra uma etapa futura.

_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class ContractMatchEntry:
    method: str
    canonical_path: str
    status: MatchStatus
    sheet: str | None = None
    declared_path: str | None = None
    # Preenchido só quando status == AMBIGUOUS.
    candidate_sheets: tuple[str, ...] = ()


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


def build_contract_match_report(
    source_file: str, results: tuple[ContractMatchResult, ...]
) -> ContractMatchReport:
    entries = tuple(_to_entry(result) for result in results)
    summary = ContractMatchSummary(
        total=len(entries),
        matched=sum(1 for entry in entries if entry.status is MatchStatus.MATCHED),
        not_found=sum(1 for entry in entries if entry.status is MatchStatus.NOT_FOUND),
        ambiguous=sum(1 for entry in entries if entry.status is MatchStatus.AMBIGUOUS),
    )
    return ContractMatchReport(
        schema_version=_SCHEMA_VERSION, source_file=source_file, summary=summary, entries=entries
    )


def _to_entry(result: ContractMatchResult) -> ContractMatchEntry:
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
        )
    if status is MatchStatus.AMBIGUOUS:
        return ContractMatchEntry(
            method=method,
            canonical_path=canonical_path,
            status=status,
            candidate_sheets=tuple(candidate.source_sheet for candidate in result.candidates),
        )
    return ContractMatchEntry(method=method, canonical_path=canonical_path, status=status)
