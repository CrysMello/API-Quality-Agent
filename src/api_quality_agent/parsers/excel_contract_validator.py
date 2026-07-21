from api_quality_agent.domain.models import ContractValidationIssue, DeclaredContractCatalog
from api_quality_agent.parsers.excel_contract_normalization import (
    map_declared_type,
    normalize_label,
    normalize_sequencial,
)
from api_quality_agent.parsers.excel_contract_parser import RawContractRow

# R2-03: ExcelContractValidator opera sobre as raw_rows (produzidas pelo
# ExcelContractParser antes da árvore ser montada) e sobre o
# DeclaredContractCatalog já construído. Não conhece Collection nem Postman
# — puramente sobre o que está declarado na planilha.
#
# ContractValidationIssue vive em domain/models/ (não aqui) porque, a partir
# da R2-09A, é consumida também pela camada de reporting — mantê-la nos
# parsers criaria uma dependência reporting -> parsers, invertendo a direção
# correta (tudo depende de domínio, domínio não depende de nada).


class ExcelContractValidator:
    def validate(
        self, raw_rows: tuple[RawContractRow, ...], catalog: DeclaredContractCatalog
    ) -> tuple[ContractValidationIssue, ...]:
        issues: list[ContractValidationIssue] = []
        issues.extend(self._validate_types(raw_rows))
        issues.extend(self._validate_sequencial_and_hierarchy(raw_rows))
        issues.extend(self._validate_arrays(raw_rows))
        issues.extend(self._validate_required_path_parameters(raw_rows))
        issues.extend(self._validate_multiple_response_sections(raw_rows))
        issues.extend(self._validate_duplicate_endpoints(catalog))
        return tuple(issues)

    # --- tipos --------------------------------------------------------------------

    def _validate_types(self, raw_rows: tuple[RawContractRow, ...]) -> list[ContractValidationIssue]:
        issues = []
        for row in raw_rows:
            if map_declared_type(row.formato_raw) is None:
                issues.append(
                    ContractValidationIssue(
                        severity="error",
                        sheet=row.sheet,
                        section=row.section,
                        row_number=row.row_number,
                        field="Formato",
                        message=f"Tipo desconhecido: {row.formato_raw!r}.",
                    )
                )
        return issues

    # --- sequencial, pais e filhos --------------------------------------------------------------------

    def _validate_sequencial_and_hierarchy(
        self, raw_rows: tuple[RawContractRow, ...]
    ) -> list[ContractValidationIssue]:
        issues: list[ContractValidationIssue] = []
        for (sheet, section), rows in self._group_by_section(raw_rows).items():
            parsed: dict[tuple[int, ...], RawContractRow] = {}
            for row in rows:
                sequencial = normalize_sequencial(row.sequencial_raw)
                if sequencial is None:
                    issues.append(
                        ContractValidationIssue(
                            severity="error",
                            sheet=sheet,
                            section=section,
                            row_number=row.row_number,
                            field="Sequencial",
                            message=f"Sequencial inválido: {row.sequencial_raw!r}.",
                        )
                    )
                    continue
                if sequencial in parsed:
                    issues.append(
                        ContractValidationIssue(
                            severity="error",
                            sheet=sheet,
                            section=section,
                            row_number=row.row_number,
                            field="Sequencial",
                            message=(
                                f"Sequencial duplicado: {row.sequencial_raw!r} "
                                f"(já usado na linha {parsed[sequencial].row_number})."
                            ),
                        )
                    )
                    continue
                parsed[sequencial] = row

            for sequencial, row in parsed.items():
                if len(sequencial) > 1 and sequencial[:-1] not in parsed:
                    parent_label = ".".join(str(part) for part in sequencial[:-1])
                    issues.append(
                        ContractValidationIssue(
                            severity="error",
                            sheet=sheet,
                            section=section,
                            row_number=row.row_number,
                            field="Sequencial",
                            message=(
                                f"Pai não encontrado para o sequencial {row.sequencial_raw!r} "
                                f"(esperado: {parent_label})."
                            ),
                        )
                    )
        return issues

    # --- arrays --------------------------------------------------------------------

    def _validate_arrays(self, raw_rows: tuple[RawContractRow, ...]) -> list[ContractValidationIssue]:
        issues: list[ContractValidationIssue] = []
        for (sheet, section), rows in self._group_by_section(raw_rows).items():
            parsed_sequenciais = {
                sequencial
                for row in rows
                if (sequencial := normalize_sequencial(row.sequencial_raw)) is not None
            }
            for row in rows:
                if map_declared_type(row.formato_raw) != "array":
                    continue
                sequencial = normalize_sequencial(row.sequencial_raw)
                if sequencial is None:
                    continue
                has_child = any(
                    len(candidate) == len(sequencial) + 1 and candidate[:-1] == sequencial
                    for candidate in parsed_sequenciais
                )
                if not has_child:
                    issues.append(
                        ContractValidationIssue(
                            severity="warning",
                            sheet=sheet,
                            section=section,
                            row_number=row.row_number,
                            field="Formato",
                            message=f"Array {row.name_raw!r} não tem nenhum filho declarado.",
                        )
                    )
        return issues

    # --- obrigatórios (path params) --------------------------------------------------------------------

    def _validate_required_path_parameters(
        self, raw_rows: tuple[RawContractRow, ...]
    ) -> list[ContractValidationIssue]:
        issues = []
        for row in raw_rows:
            if row.section != "path":
                continue
            sequencial = normalize_sequencial(row.sequencial_raw)
            if sequencial is None or len(sequencial) != 1:
                continue
            if normalize_label(row.obrigatoriedade_raw) != "sim":
                issues.append(
                    ContractValidationIssue(
                        severity="warning",
                        sheet=row.sheet,
                        section=row.section,
                        row_number=row.row_number,
                        field="Obrigatoriedade",
                        message=(
                            f"Path param {row.name_raw!r} está marcado como não-obrigatório; "
                            "parâmetros de path normalmente exigem presença."
                        ),
                    )
                )
        return issues

    # --- múltiplos status --------------------------------------------------------------------

    def _validate_multiple_response_sections(
        self, raw_rows: tuple[RawContractRow, ...]
    ) -> list[ContractValidationIssue]:
        statuses_by_sheet: dict[str, set[str]] = {}
        for row in raw_rows:
            if row.section.startswith("response_"):
                status = row.section.removeprefix("response_")
                statuses_by_sheet.setdefault(row.sheet, set()).add(status)

        issues = []
        for sheet, statuses in statuses_by_sheet.items():
            for status in sorted(status for status in statuses if status != "200"):
                issues.append(
                    ContractValidationIssue(
                        severity="warning",
                        sheet=sheet,
                        section=f"response_{status}",
                        row_number=None,
                        field=None,
                        message=(
                            f"Seção de resposta para o status {status} foi reconhecida, mas é "
                            "ignorada nesta Release (R2-00B: só HTTP 200 é usado)."
                        ),
                    )
                )
        return issues

    # --- endpoints duplicados (usa o catálogo) --------------------------------------------------------------------

    def _validate_duplicate_endpoints(
        self, catalog: DeclaredContractCatalog
    ) -> list[ContractValidationIssue]:
        issues = []
        seen: dict[tuple[str, str], str] = {}
        for contract in catalog.contracts:
            key = (contract.method.upper(), contract.path)
            if key in seen:
                issues.append(
                    ContractValidationIssue(
                        severity="error",
                        sheet=contract.source_sheet,
                        section=None,
                        row_number=None,
                        field=None,
                        message=(
                            f"Endpoint duplicado: {contract.method} {contract.path} já declarado "
                            f"na aba {seen[key]!r}."
                        ),
                    )
                )
            else:
                seen[key] = contract.source_sheet
        return issues

    @staticmethod
    def _group_by_section(
        raw_rows: tuple[RawContractRow, ...],
    ) -> dict[tuple[str, str], list[RawContractRow]]:
        groups: dict[tuple[str, str], list[RawContractRow]] = {}
        for row in raw_rows:
            groups.setdefault((row.sheet, row.section), []).append(row)
        return groups
