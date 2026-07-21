import json

from api_quality_agent.application.orchestration import AgentOrchestrator
from api_quality_agent.domain.models import (
    DeclaredContractCatalog,
    DeclaredEndpointContract,
    DeclaredRequestContract,
    DeclaredResponseContract,
    DeclaredSchema,
    ExecutionContext,
    ExecutionMode,
)
from api_quality_agent.domain.services import (
    ApiAnalysisEngine,
    CanonicalEndpointNormalizer,
    ContractEndpointMatcher,
    DiffEngine,
    ExcelSchemaProvider,
    InferenceSchemaProvider,
    ManagedBlockMerger,
    SchemaInferenceEngine,
    TestStrategyEngine,
)
from api_quality_agent.generators import PostmanTestGenerator
from api_quality_agent.parsers import PostmanCollectionParser

# R2-06: garante que a troca de SchemaInferenceEngine por SchemaProvider no
# AgentOrchestrator é retrocompatível (callsites existentes continuam
# funcionando sem mudança) e que a nova capacidade (schema declarado via
# ExcelSchemaProvider) funciona ponta a ponta.


def _parse(items: list) -> object:
    document = {
        "info": {
            "name": "Col",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": items,
    }
    return PostmanCollectionParser().parse_text(json.dumps(document))


def _execution_context(**overrides) -> ExecutionContext:
    params = {"mode": ExecutionMode.ONLINE, "source": "postman", "id_factory": lambda: "exec-fixed"}
    params.update(overrides)
    return ExecutionContext.create(**params)


def test_passing_a_bare_schema_inference_engine_still_works_unchanged():
    # Exatamente o mesmo callsite usado em todo o resto do projeto hoje
    # (bootstrap.py, conftest.py de aceitação, outros testes) — precisa
    # continuar funcionando sem nenhuma mudança de código.
    document = _parse(
        [
            {
                "name": "Criar pet",
                "id": "r1",
                "request": {"method": "POST", "url": "https://x/pets"},
                "response": [
                    {"name": "ok", "status": "OK", "code": 201, "header": [], "body": '{"id": 1}'}
                ],
            }
        ]
    )
    orchestrator = AgentOrchestrator(
        ApiAnalysisEngine(),
        SchemaInferenceEngine(),
        TestStrategyEngine(),
        PostmanTestGenerator(),
        ManagedBlockMerger(),
        DiffEngine(),
    )

    result = orchestrator.process(document, _execution_context())

    outcome = result.endpoint_outcomes[0]
    assert outcome.error is None
    assert "pm.response.to.have.status(201)" in outcome.generated_script.script


def test_bare_schema_inference_engine_and_wrapped_inference_provider_produce_identical_scripts():
    document = _parse(
        [
            {
                "name": "Criar pet",
                "id": "r1",
                "request": {"method": "POST", "url": "https://x/pets"},
                "response": [
                    {"name": "ok", "status": "OK", "code": 201, "header": [], "body": '{"id": 1}'}
                ],
            }
        ]
    )

    def _build(schema_component):
        return AgentOrchestrator(
            ApiAnalysisEngine(),
            schema_component,
            TestStrategyEngine(),
            PostmanTestGenerator(),
            ManagedBlockMerger(),
            DiffEngine(),
        )

    legacy = _build(SchemaInferenceEngine())
    explicit_provider = _build(InferenceSchemaProvider(SchemaInferenceEngine()))

    result_legacy = legacy.process(document, _execution_context(id_factory=lambda: "exec-a"))
    result_explicit = explicit_provider.process(document, _execution_context(id_factory=lambda: "exec-b"))

    assert (
        result_legacy.endpoint_outcomes[0].generated_script.script
        == result_explicit.endpoint_outcomes[0].generated_script.script
    )


def test_excel_schema_provider_drives_generation_from_declared_schema_instead_of_examples():
    # A request tem um Example salvo só com status 200 e corpo vazio — dá a
    # evidência de status que o TestStrategyEngine já exige hoje (mesma
    # exigência de sempre, nada relacionado ao SchemaProvider), mas o
    # ExcelSchemaProvider nunca olha pros exemplos: o schema usado pra gerar
    # a asserção de campo precisa vir só do contrato declarado.
    document = _parse(
        [
            {
                "name": "Buscar pet",
                "id": "r1",
                "request": {"method": "GET", "url": "https://x/pets/1"},
                "response": [
                    {"name": "ok", "status": "OK", "code": 200, "header": [], "body": "{}"}
                ],
            }
        ]
    )

    response_schema = DeclaredSchema(
        type="object",
        required=True,
        properties=(DeclaredSchema(type="string", required=True, name="id"),),
    )
    contract = DeclaredEndpointContract(
        method="GET",
        path="/pets/{id}",
        request=DeclaredRequestContract(),
        response=DeclaredResponseContract(schema=response_schema),
        source_sheet="Planilha1",
    )
    catalog = DeclaredContractCatalog(source_file="contrato.xlsx", contracts=(contract,))
    normalizer = CanonicalEndpointNormalizer()
    excel_provider = ExcelSchemaProvider(
        catalog=catalog, matcher=ContractEndpointMatcher(normalizer), normalizer=normalizer
    )

    orchestrator = AgentOrchestrator(
        ApiAnalysisEngine(),
        excel_provider,
        TestStrategyEngine(),
        PostmanTestGenerator(),
        ManagedBlockMerger(),
        DiffEngine(),
    )

    result = orchestrator.process(document, _execution_context())

    outcome = result.endpoint_outcomes[0]
    assert outcome.error is None
    assert outcome.generated_script is not None
    assert "id" in outcome.generated_script.script


def test_excel_schema_provider_without_match_falls_back_to_no_schema_not_an_error():
    # Sem contrato declarado pra esse endpoint e sem Example salvo: gera sem
    # schema (comportamento seguro), nunca lança erro.
    document = _parse(
        [{"name": "Sem contrato", "id": "r1", "request": {"method": "GET", "url": "https://x/desconhecido"}}]
    )
    catalog = DeclaredContractCatalog(source_file="contrato.xlsx", contracts=())
    normalizer = CanonicalEndpointNormalizer()
    excel_provider = ExcelSchemaProvider(
        catalog=catalog, matcher=ContractEndpointMatcher(normalizer), normalizer=normalizer
    )

    orchestrator = AgentOrchestrator(
        ApiAnalysisEngine(),
        excel_provider,
        TestStrategyEngine(),
        PostmanTestGenerator(),
        ManagedBlockMerger(),
        DiffEngine(),
    )

    result = orchestrator.process(document, _execution_context())

    outcome = result.endpoint_outcomes[0]
    assert outcome.error is None
