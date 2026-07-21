import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

from api_quality_agent.domain.models import (
    DeclaredContractCatalog,
    DeclaredEndpointContract,
    DeclaredParameter,
    DeclaredRequestContract,
    DeclaredResponseContract,
    DeclaredSchema,
    ParameterLocation,
)
from api_quality_agent.parsers.excel_contract_normalization import (
    map_declared_type,
    normalize_label,
    normalize_sequencial,
)

# R2-02/R2-03: Excel -> ExcelContractParser -> ExcelParseResult
# (raw_rows + DeclaredContractCatalog). Sem validação formal de consistência
# (isso é responsabilidade do ExcelContractValidator, que consome as
# raw_rows), sem matcher, sem CLI.
#
# Decisão de escopo R2-00B: só a seção "Resposta ... Status code 200 ..." é
# convertida em schema. Outras seções de resposta (400, 404, 500 etc.) são
# reconhecidas (pra não quebrar a leitura da aba), mas descartadas do
# catálogo — permanecem apenas nas raw_rows, à disposição do validador.

_SECTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "header": re.compile(r"requisicao\s*\(\s*header\s*\)"),
    "path": re.compile(r"requisicao\s*\(\s*path param\s*\)"),
    "query": re.compile(r"requisicao\s*\(\s*query param\s*\)"),
    "body": re.compile(r"requisicao\s*\(?\s*body\s*\)?"),
}
_RESPONSE_SECTION_PATTERN = re.compile(r"resposta.*status\s*code\s*(\d+)")

_SUCCESS_STATUS_CODE = "200"


@dataclass(frozen=True)
class RawContractRow:
    # Uma linha de dado observada numa seção da planilha, preservada sem
    # filtragem (mesmo linhas com sequencial duplicado, órfão, ou tipo
    # desconhecido) — é sobre isso que o ExcelContractValidator opera.
    sheet: str
    section: str
    row_number: int
    sequencial_raw: str
    name_raw: str | None
    formato_raw: str | None
    obrigatoriedade_raw: str | None


@dataclass(frozen=True)
class ExcelParseResult:
    raw_rows: tuple[RawContractRow, ...]
    catalog: DeclaredContractCatalog


class _NormalizedRow:
    __slots__ = ("sequencial", "name", "type", "required")

    def __init__(self, sequencial: tuple[int, ...], name: str, type_: str, required: bool) -> None:
        self.sequencial = sequencial
        self.name = name
        self.type = type_
        self.required = required


class ExcelContractParser:
    def parse(self, file_path: str | Path) -> ExcelParseResult:
        path = Path(file_path)
        workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
        try:
            all_raw_rows: list[RawContractRow] = []
            contracts: list[DeclaredEndpointContract] = []
            for worksheet in workbook.worksheets:
                sheet_raw_rows, contract = self._parse_sheet(worksheet)
                all_raw_rows.extend(sheet_raw_rows)
                if contract is not None:
                    contracts.append(contract)
        finally:
            workbook.close()

        catalog = DeclaredContractCatalog(source_file=str(path), contracts=tuple(contracts))
        return ExcelParseResult(raw_rows=tuple(all_raw_rows), catalog=catalog)

    def _parse_sheet(
        self, worksheet: Worksheet
    ) -> tuple[list[RawContractRow], DeclaredEndpointContract | None]:
        rows = list(worksheet.iter_rows(values_only=True))

        method, uri = self._find_metadata(rows)
        sections = self._split_sections(worksheet.title, rows)
        raw_rows = [row for rows_in_section in sections.values() for row in rows_in_section]

        if not method or not uri:
            return raw_rows, None

        normalized = {key: self._normalize_section(rows_in_section) for key, rows_in_section in sections.items()}

        request = DeclaredRequestContract(
            headers=self._build_parameters(normalized.get("header", []), ParameterLocation.HEADER),
            path_parameters=self._build_parameters(normalized.get("path", []), ParameterLocation.PATH),
            query_parameters=self._build_parameters(normalized.get("query", []), ParameterLocation.QUERY),
            body_schema=self._build_root_schema(normalized.get("body", [])),
        )
        response = DeclaredResponseContract(
            schema=self._build_root_schema(normalized.get(f"response_{_SUCCESS_STATUS_CODE}", []))
        )

        contract = DeclaredEndpointContract(
            method=method,
            path=uri,
            request=request,
            response=response,
            source_sheet=worksheet.title,
        )
        return raw_rows, contract

    def _find_metadata(self, rows: list[tuple[Any, ...]]) -> tuple[str | None, str | None]:
        method: str | None = None
        uri: str | None = None
        for row in rows:
            for index, cell in enumerate(row):
                label = normalize_label(cell)
                if label == "uri" and uri is None:
                    uri = self._first_non_empty_after(row, index)
                elif label == "metodo" and method is None:
                    method = self._first_non_empty_after(row, index)
            if method and uri:
                break
        return method, uri

    @staticmethod
    def _first_non_empty_after(row: tuple[Any, ...], index: int) -> str | None:
        for value in row[index + 1 :]:
            if value is not None and str(value).strip():
                return str(value).strip()
        return None

    def _split_sections(
        self, sheet_title: str, rows: list[tuple[Any, ...]]
    ) -> dict[str, list[RawContractRow]]:
        sections: dict[str, list[RawContractRow]] = {}
        current_key: str | None = None
        column_map: dict[str, int] | None = None

        for row_number, row in enumerate(rows, start=1):
            joined = " ".join(normalize_label(cell) for cell in row if cell is not None).strip()
            if not joined:
                continue

            section_key = self._match_section(joined)
            if section_key is not None:
                current_key = section_key
                column_map = None
                sections.setdefault(current_key, [])
                continue

            if current_key is None:
                continue

            header_map = self._match_header_row(row)
            if header_map is not None:
                column_map = header_map
                continue

            if column_map is not None:
                raw_row = self._read_raw_row(sheet_title, current_key, row_number, row, column_map)
                if raw_row is not None:
                    sections[current_key].append(raw_row)

        return sections

    @staticmethod
    def _match_section(joined: str) -> str | None:
        for key, pattern in _SECTION_PATTERNS.items():
            if pattern.search(joined):
                return key
        match = _RESPONSE_SECTION_PATTERN.search(joined)
        if match:
            return f"response_{match.group(1)}"
        return None

    @staticmethod
    def _match_header_row(row: tuple[Any, ...]) -> dict[str, int] | None:
        mapping: dict[str, int] = {}
        for index, cell in enumerate(row):
            label = normalize_label(cell)
            if label == "sequencial":
                mapping["sequencial"] = index
            elif label == "nome do campo":
                mapping["nome"] = index
            elif label == "formato":
                mapping["formato"] = index
            elif label.startswith("obrigatori"):
                mapping["obrigatoriedade"] = index

        required_keys = {"sequencial", "nome", "formato", "obrigatoriedade"}
        if required_keys.issubset(mapping):
            return mapping
        return None

    @staticmethod
    def _read_raw_row(
        sheet: str, section: str, row_number: int, row: tuple[Any, ...], column_map: dict[str, int]
    ) -> RawContractRow | None:
        def _cell(key: str) -> Any:
            index = column_map[key]
            return row[index] if index < len(row) else None

        sequencial_cell = _cell("sequencial")
        name_cell = _cell("nome")
        formato_cell = _cell("formato")
        obrigatoriedade_cell = _cell("obrigatoriedade")

        if all(
            cell is None or not str(cell).strip()
            for cell in (sequencial_cell, name_cell, formato_cell, obrigatoriedade_cell)
        ):
            return None

        return RawContractRow(
            sheet=sheet,
            section=section,
            row_number=row_number,
            sequencial_raw=str(sequencial_cell).strip() if sequencial_cell is not None else "",
            name_raw=str(name_cell).strip() if name_cell is not None else None,
            formato_raw=str(formato_cell).strip() if formato_cell is not None else None,
            obrigatoriedade_raw=(
                str(obrigatoriedade_cell).strip() if obrigatoriedade_cell is not None else None
            ),
        )

    @staticmethod
    def _normalize_section(raw_rows: list[RawContractRow]) -> list[_NormalizedRow]:
        normalized: list[_NormalizedRow] = []
        for raw in raw_rows:
            sequencial = normalize_sequencial(raw.sequencial_raw)
            schema_type = map_declared_type(raw.formato_raw)
            if sequencial is None or not raw.name_raw or schema_type is None:
                continue
            required = normalize_label(raw.obrigatoriedade_raw) == "sim"
            normalized.append(
                _NormalizedRow(sequencial=sequencial, name=raw.name_raw, type_=schema_type, required=required)
            )
        return normalized

    def _build_root_schema(self, records: list[_NormalizedRow]) -> DeclaredSchema | None:
        if not records:
            return None
        by_seq = {record.sequencial: record for record in records}
        roots = sorted(seq for seq in by_seq if len(seq) == 1)
        if not roots:
            return None
        properties = tuple(self._build_node(by_seq, seq) for seq in roots)
        return DeclaredSchema(type="object", required=True, properties=properties)

    def _build_node(
        self, by_seq: dict[tuple[int, ...], _NormalizedRow], seq: tuple[int, ...]
    ) -> DeclaredSchema:
        record = by_seq[seq]
        children = sorted(
            candidate
            for candidate in by_seq
            if len(candidate) == len(seq) + 1 and candidate[:-1] == seq
        )

        if record.type == "object":
            properties = tuple(self._build_node(by_seq, child) for child in children)
            return DeclaredSchema(
                type="object", required=record.required, name=record.name, properties=properties
            )
        if record.type == "array":
            item_properties = tuple(self._build_node(by_seq, child) for child in children)
            items = (
                DeclaredSchema(type="object", required=True, properties=item_properties)
                if item_properties
                else None
            )
            return DeclaredSchema(type="array", required=record.required, name=record.name, items=items)
        return DeclaredSchema(type=record.type, required=record.required, name=record.name)

    def _build_parameters(
        self, records: list[_NormalizedRow], location: ParameterLocation
    ) -> tuple[DeclaredParameter, ...]:
        if not records:
            return ()
        by_seq = {record.sequencial: record for record in records}
        roots = sorted(seq for seq in by_seq if len(seq) == 1)
        parameters = []
        for seq in roots:
            node = self._build_node(by_seq, seq)
            parameters.append(
                DeclaredParameter(
                    name=node.name or by_seq[seq].name,
                    location=location,
                    required=node.required,
                    schema=node,
                )
            )
        return tuple(parameters)
