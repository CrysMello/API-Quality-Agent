"""Release 2 (Integração de Contratos Excel) — jornada completa ponta a
ponta: contrato declarado numa planilha Excel, pareado por método+path com
uma request real (simulada) de uma Collection Postman, usando o schema
declarado em vez de inferência quando há match — e caindo pra inferência
normalmente quando não há.

Não faz parte da numeração original dos 20 cenários do MVP (SAD original) —
é uma extensão posterior, testada aqui com os mesmos princípios de
aceitação: componentes reais compostos como um wiring de CLI faria (aqui,
GenerateTestsWithContractUseCase, o mesmo use case que bootstrap.py usa
para `generate --contract-file`), só a API do Postman simulada por um
servidor HTTP local.
"""

import json
from pathlib import Path

import openpyxl
from conftest import WORKSPACE_ID, WORKSPACE_NAME, build_app

from api_quality_agent.application.use_cases import GenerateTestsWithContractUseCase
from api_quality_agent.domain.services import (
    ApiAnalysisEngine,
    DiffEngine,
    ManagedBlockMerger,
    SchemaInferenceEngine,
    TestStrategyEngine,
)
from api_quality_agent.generators import PostmanTestGenerator
from api_quality_agent.parsers import ExcelContractParser

_HEADER_ROW = ["Sequencial", "Nome do campo", "Formato", "Tamanho", "Obrigatoriedade", "Regras (Domínio)"]

_COLLECTION_ID = "col-contract"
_COLLECTION_NAME = "Pets API (contrato)"


def _collection_payload() -> dict:
    # Example salvo com status 200: dá a evidência de status que o
    # TestStrategyEngine já exige hoje pra gerar qualquer asserção (mesma
    # exigência de sempre, nada relacionado ao SchemaProvider). A prova de
    # que o schema usado num teste específico é o declarado (não inferido)
    # é o Contract Match Report, verificado nos testes abaixo (MATCHED vs.
    # NOT_FOUND) — não o conteúdo do script em si.
    request: dict = {
        "name": "Buscar pet",
        "id": "req-pet",
        "request": {"method": "GET", "url": "https://api.exemplo.com/pets/:petId"},
        "response": [{"name": "ok", "status": "OK", "code": 200, "header": [], "body": '{"id": 1}'}],
    }
    return {
        "info": {
            "name": _COLLECTION_NAME,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": [request],
    }


def _configure_server(server) -> None:
    server.set_route("/me", status=200, body={"user": {"id": 1, "username": "qa"}})
    server.set_route(
        "/workspaces", status=200, body={"workspaces": [{"id": WORKSPACE_ID, "name": WORKSPACE_NAME}]}
    )
    server.set_route(
        f"/collections?workspace={WORKSPACE_ID}",
        status=200,
        body={"collections": [{"id": _COLLECTION_ID, "uid": _COLLECTION_ID, "name": _COLLECTION_NAME}]},
    )
    server.set_route(
        f"/collections/{_COLLECTION_ID}", status=200, body={"collection": _collection_payload()}
    )


def _write_contract_file(tmp_path) -> str:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Pets"
    rows = [
        ["URI", "/pets/{{petId}}"],
        ["Método", "GET"],
        ["Resposta caso HTTP Status code 200 - OK"],
        _HEADER_ROW,
        ["1", "dado", "Objeto", None, "SIM"],
        ["1.1", "id", "Alfanumerico", 10, "SIM"],
        ["1.2", "nome", "Alfanumerico", 50, "SIM"],
    ]
    for row in rows:
        sheet.append(row)
    path = tmp_path / "contrato.xlsx"
    workbook.save(path)
    return str(path)


def _build_generate_with_contract_use_case(app) -> GenerateTestsWithContractUseCase:
    # Mesma composição que bootstrap.py monta para `generate --contract-file`
    # (online) — reaproveitando as dependências já expostas por build_app(),
    # sem alterar conftest.py.
    return GenerateTestsWithContractUseCase(
        ExcelContractParser(),
        ApiAnalysisEngine(),
        SchemaInferenceEngine(),
        TestStrategyEngine(),
        PostmanTestGenerator(),
        ManagedBlockMerger(),
        DiffEngine(),
        app.artifact_repository,
        get_current_workspace_use_case=app.get_current_workspace,
        resolve_collection_use_case=app.resolve_collection,
        collection_repository=app.collection_repository,
    )


def test_generate_with_excel_contract_matches_a_real_collection_request(
    postman_test_server, tmp_path
):
    _configure_server(postman_test_server)
    app = build_app(postman_test_server, tmp_path)
    app.select_workspace.execute(workspace_id=WORKSPACE_ID)
    contract_file = _write_contract_file(tmp_path)

    use_case = _build_generate_with_contract_use_case(app)
    result = use_case.execute_online(contract_file=contract_file, collection_id=_COLLECTION_ID)

    outcome = result.endpoint_outcomes[0]
    assert outcome.error is None
    assert outcome.generated_script is not None
    assert "pm.test(" in outcome.generated_script.script

    # A prova de que o endpoint foi pareado com o contrato declarado (não só
    # gerado por inferência, coincidentemente) é o Contract Match Report,
    # salvo automaticamente junto dos demais artefatos.
    match_json = next(
        location for location in result.artifact_locations if location.path.endswith("contract-match-report.json")
    )
    payload = json.loads(Path(match_json.path).read_text(encoding="utf-8"))
    assert payload["summary"]["matched"] == 1
    assert payload["matches"][0]["status"] == "MATCHED"
    assert payload["matches"][0]["sheet"] == "Pets"

    # O relatório também é salvo em HTML, na mesma pasta de execução.
    html_report = next(
        location for location in result.artifact_locations if location.path.endswith("contract-match-report.html")
    )
    assert Path(html_report.path).exists()


def test_generate_with_excel_contract_falls_back_to_inference_for_unmatched_requests(
    postman_test_server, tmp_path
):
    # Contrato aponta pra um endpoint que não existe na Collection — a
    # request real (com Example salvo) precisa continuar gerando pela
    # inferência de sempre (FallbackSchemaProvider cai pra
    # InferenceSchemaProvider), provando que ausência de match não quebra
    # nem esvazia o que já funcionava antes desta funcionalidade existir.
    _configure_server(postman_test_server)
    app = build_app(postman_test_server, tmp_path)
    app.select_workspace.execute(workspace_id=WORKSPACE_ID)

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "OutroEndpoint"
    for row in [["URI", "/nao-existe"], ["Método", "GET"]]:
        sheet.append(row)
    contract_file = tmp_path / "contrato_sem_match.xlsx"
    workbook.save(contract_file)

    use_case = _build_generate_with_contract_use_case(app)
    result = use_case.execute_online(contract_file=str(contract_file), collection_id=_COLLECTION_ID)

    outcome = result.endpoint_outcomes[0]
    assert outcome.error is None
    # A request TEM Example salvo — sem contrato pareado, o fallback pra
    # inferência precisa gerar a asserção normalmente, como sempre gerou.
    assert "pm.test(" in outcome.generated_script.script
    assert "pm.response.to.have.status(200)" in outcome.generated_script.script

    match_json = next(
        location for location in result.artifact_locations if location.path.endswith("contract-match-report.json")
    )
    payload = json.loads(Path(match_json.path).read_text(encoding="utf-8"))
    assert payload["summary"]["not_found"] == 1
