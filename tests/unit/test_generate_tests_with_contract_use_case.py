import json
from pathlib import Path

import openpyxl
import pytest

from api_quality_agent.adapters.filesystem import LocalArtifactRepository
from api_quality_agent.application.use_cases import GenerateTestsWithContractUseCase
from api_quality_agent.domain.exceptions import InputError
from api_quality_agent.domain.services import (
    ApiAnalysisEngine,
    DiffEngine,
    ManagedBlockMerger,
    SchemaInferenceEngine,
    TestStrategyEngine,
)
from api_quality_agent.generators import PostmanTestGenerator
from api_quality_agent.parsers import ExcelContractParser, PostmanCollectionParser
from api_quality_agent.domain.models import InputOrigin, ResolvedInput

_HEADER_ROW = ["Sequencial", "Nome do campo", "Formato", "Tamanho", "Obrigatoriedade", "Regras (Domínio)"]


def _build_contract_workbook(tmp_path, entries):
    workbook = openpyxl.Workbook()
    first = True
    for sheet_title, method, uri in entries:
        sheet = workbook.active if first else workbook.create_sheet()
        sheet.title = sheet_title
        first = False
        rows = [
            ["URI", uri],
            ["Método", method],
            ["Resposta caso HTTP Status code 200 - OK"],
            _HEADER_ROW,
            ["1", "dado", "Objeto", None, "SIM"],
            ["1.1", "id", "Alfanumerico", 10, "SIM"],
        ]
        for row in rows:
            sheet.append(row)
    path = tmp_path / "contrato.xlsx"
    workbook.save(path)
    return str(path)


def _parse_document(items):
    document = {
        "info": {
            "name": "Col",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": items,
    }
    resolved = ResolvedInput(
        origin=InputOrigin.FILE, content_type="json", name="c.json", content=json.dumps(document)
    )
    return PostmanCollectionParser().parse(resolved)


def _build_use_case(tmp_path):
    artifact_repository = LocalArtifactRepository(tmp_path / "artifacts")
    return GenerateTestsWithContractUseCase(
        ExcelContractParser(),
        ApiAnalysisEngine(),
        SchemaInferenceEngine(),
        TestStrategyEngine(),
        PostmanTestGenerator(),
        ManagedBlockMerger(),
        DiffEngine(),
        artifact_repository,
    )


def test_execute_offline_saves_a_contract_match_report_json_and_html(tmp_path):
    contract_path = _build_contract_workbook(
        tmp_path, [("Planilha1", "GET", "/v2/pet/{{petId}}")]
    )
    document = _parse_document(
        [
            {
                "name": "Buscar pet",
                "id": "r1",
                "request": {"method": "GET", "url": "https://x/v2/pet/:petId"},
                "response": [
                    {"name": "ok", "status": "OK", "code": 200, "header": [], "body": "{}"}
                ],
            }
        ]
    )

    use_case = _build_use_case(tmp_path)
    result = use_case.execute_offline(contract_file=contract_path, document=document)

    json_location = next(
        loc for loc in result.artifact_locations if loc.path.endswith("contract-match-report.json")
    )
    html_location = next(
        loc for loc in result.artifact_locations if loc.path.endswith("contract-match-report.html")
    )

    payload = json.loads(Path(json_location.path).read_text(encoding="utf-8"))
    assert payload["summary"]["matched"] == 1
    assert payload["summary"]["not_found"] == 0
    assert payload["matches"][0]["status"] == "MATCHED"

    html_content = Path(html_location.path).read_text(encoding="utf-8")
    assert "MATCHED" in html_content


def test_execute_offline_reports_not_found_when_request_has_no_declared_contract(tmp_path):
    contract_path = _build_contract_workbook(tmp_path, [("Planilha1", "GET", "/v2/outra-coisa")])
    document = _parse_document(
        [{"name": "Buscar pet", "id": "r1", "request": {"method": "GET", "url": "https://x/v2/pet/1"}}]
    )

    use_case = _build_use_case(tmp_path)
    result = use_case.execute_offline(contract_file=contract_path, document=document)

    json_location = next(
        loc for loc in result.artifact_locations if loc.path.endswith("contract-match-report.json")
    )
    payload = json.loads(Path(json_location.path).read_text(encoding="utf-8"))
    assert payload["summary"]["not_found"] == 1
    assert payload["summary"]["matched"] == 0


def test_match_report_is_saved_in_the_same_execution_folder_as_scripts_and_diff(tmp_path):
    contract_path = _build_contract_workbook(
        tmp_path, [("Planilha1", "GET", "/v2/pet/{{petId}}")]
    )
    document = _parse_document(
        [{"name": "Buscar pet", "id": "r1", "request": {"method": "GET", "url": "https://x/v2/pet/:petId"}}]
    )

    use_case = _build_use_case(tmp_path)
    result = use_case.execute_offline(contract_file=contract_path, document=document)

    directories = {Path(loc.path).parent.parent for loc in result.artifact_locations}
    assert len(directories) == 1  # todos os artefatos (scripts/diffs/contracts) na mesma pasta de execução


def test_execute_online_without_workspace_dependencies_raises_input_error(tmp_path):
    use_case = _build_use_case(tmp_path)

    with pytest.raises(InputError):
        use_case.execute_online(contract_file="qualquer.xlsx", collection_id="abc")
