import re
import unicodedata
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

# R2-02: só o caminho Excel -> ExcelContractParser -> DeclaredContractCatalog.
# Sem validação formal de consistência (ExcelContractValidator), sem matcher,
# sem CLI — uma aba sem URI/Método utilizável simplesmente não vira contrato,
# em vez de levantar um erro estruturado (isso fica pra uma fase posterior).
#
# Decisão de escopo R2-00B: só a seção "Resposta ... Status code 200 ..." é
# convertida em schema. Outras seções de resposta (400, 404, 500 etc.) são
# reconhecidas (pra não quebrar a leitura da aba), mas descartadas.

_TYPE_MAP: dict[str, str] = {
    "alfanumerico": "string",
    "texto": "string",
    "numerico": "number",
    "inteiro": "integer",
    "booleano": "boolean",
    "data": "string",
    "datahora": "string",
    "data e hora": "string",
    "objeto": "object",
    "arraylist": "array",
    "lista": "array",
}

_SECTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "header": re.compile(r"requisicao\s*\(\s*header\s*\)"),
    "path": re.compile(r"requisicao\s*\(\s*path param\s*\)"),
    "query": re.compile(r"requisicao\s*\(\s*query param\s*\)"),
    "body": re.compile(r"requisicao\s*\(?\s*body\s*\)?"),
}
_RESPONSE_SECTION_PATTERN = re.compile(r"resposta.*status\s*code\s*(\d+)")

_SuccessStatusCode = "200"


def _normalize_label(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().casefold()
    without_accents = "".join(
        char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", without_accents).strip()


def _map_type(raw_formato: Any) -> str | None:
    return _TYPE_MAP.get(_normalize_label(raw_formato))


def _normalize_sequencial(value: Any) -> tuple[int, ...] | None:
    if isinstance(value, (int, float)):
        return (int(value),)
    text = str(value).strip()
    if not text:
        return None
    try:
        return tuple(int(part) for part in text.split("."))
    except ValueError:
        return None


class _Row:
    __slots__ = ("sequencial", "name", "type", "required")

    def __init__(self, sequencial: tuple[int, ...], name: str, type_: str, required: bool) -> None:
        self.sequencial = sequencial
        self.name = name
        self.type = type_
        self.required = required


class ExcelContractParser:
    def parse(self, file_path: str | Path) -> DeclaredContractCatalog:
        path = Path(file_path)
        workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
        try:
            contracts = tuple(
                contract
                for worksheet in workbook.worksheets
                if (contract := self._parse_sheet(worksheet)) is not None
            )
        finally:
            workbook.close()
        return DeclaredContractCatalog(source_file=str(path), contracts=contracts)

    def _parse_sheet(self, worksheet: Worksheet) -> DeclaredEndpointContract | None:
        rows = list(worksheet.iter_rows(values_only=True))

        method, uri = self._find_metadata(rows)
        if not method or not uri:
            return None

        sections = self._split_sections(rows)

        request = DeclaredRequestContract(
            headers=self._build_parameters(sections.get("header", []), ParameterLocation.HEADER),
            path_parameters=self._build_parameters(sections.get("path", []), ParameterLocation.PATH),
            query_parameters=self._build_parameters(sections.get("query", []), ParameterLocation.QUERY),
            body_schema=self._build_root_schema(sections.get("body", [])),
        )
        response = DeclaredResponseContract(
            schema=self._build_root_schema(sections.get(f"response_{_SuccessStatusCode}", []))
        )

        return DeclaredEndpointContract(
            method=method,
            path=uri,
            request=request,
            response=response,
            source_sheet=worksheet.title,
        )

    def _find_metadata(self, rows: list[tuple[Any, ...]]) -> tuple[str | None, str | None]:
        method: str | None = None
        uri: str | None = None
        for row in rows:
            for index, cell in enumerate(row):
                label = _normalize_label(cell)
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

    def _split_sections(self, rows: list[tuple[Any, ...]]) -> dict[str, list[_Row]]:
        sections: dict[str, list[_Row]] = {}
        current_key: str | None = None
        column_map: dict[str, int] | None = None

        for row in rows:
            joined = " ".join(_normalize_label(cell) for cell in row if cell is not None).strip()
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
                parsed_row = self._parse_data_row(row, column_map)
                if parsed_row is not None:
                    sections[current_key].append(parsed_row)

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
            label = _normalize_label(cell)
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
    def _parse_data_row(row: tuple[Any, ...], column_map: dict[str, int]) -> _Row | None:
        def _cell(key: str) -> Any:
            index = column_map[key]
            return row[index] if index < len(row) else None

        sequencial = _normalize_sequencial(_cell("sequencial"))
        name_raw = _cell("nome")
        schema_type = _map_type(_cell("formato"))

        if sequencial is None or name_raw is None or schema_type is None:
            return None

        name = str(name_raw).strip()
        if not name:
            return None

        required = _normalize_label(_cell("obrigatoriedade")) == "sim"
        return _Row(sequencial=sequencial, name=name, type_=schema_type, required=required)

    def _build_root_schema(self, records: list[_Row]) -> DeclaredSchema | None:
        if not records:
            return None
        by_seq = {record.sequencial: record for record in records}
        roots = sorted(seq for seq in by_seq if len(seq) == 1)
        if not roots:
            return None
        properties = tuple(self._build_node(by_seq, seq) for seq in roots)
        return DeclaredSchema(type="object", required=True, properties=properties)

    def _build_node(self, by_seq: dict[tuple[int, ...], _Row], seq: tuple[int, ...]) -> DeclaredSchema:
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
        self, records: list[_Row], location: ParameterLocation
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
