import json

from api_quality_agent.application.orchestration import AgentOrchestrator
from api_quality_agent.domain.models import ExecutionContext, ExecutionMode
from api_quality_agent.domain.services import (
    ApiAnalysisEngine,
    DiffEngine,
    ManagedBlockMerger,
    SchemaInferenceEngine,
    TestStrategyEngine,
)
from api_quality_agent.generators import PostmanTestGenerator
from api_quality_agent.parsers import PostmanCollectionParser


def _parse(items: list) -> object:
    document = {
        "info": {
            "name": "Col",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": items,
    }
    return PostmanCollectionParser().parse_text(json.dumps(document))


def _build_orchestrator() -> AgentOrchestrator:
    return AgentOrchestrator(
        ApiAnalysisEngine(),
        SchemaInferenceEngine(),
        TestStrategyEngine(),
        PostmanTestGenerator(),
        ManagedBlockMerger(),
        DiffEngine(),
    )


def _execution_context(**overrides) -> ExecutionContext:
    params = {
        "mode": ExecutionMode.ONLINE,
        "source": "postman",
        "id_factory": lambda: "exec-fixed",
    }
    params.update(overrides)
    return ExecutionContext.create(**params)


def test_process_generates_outcome_with_status_from_saved_example():
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
    orchestrator = _build_orchestrator()

    result = orchestrator.process(document, _execution_context())

    assert len(result.endpoint_outcomes) == 1
    outcome = result.endpoint_outcomes[0]
    assert outcome.error is None
    assert "pm.response.to.have.status(201)" in outcome.generated_script.script


def test_process_does_not_mutate_original_document():
    document = _parse(
        [{"name": "Ping", "id": "r1", "request": {"method": "GET", "url": "https://x/y"}}]
    )
    orchestrator = _build_orchestrator()

    orchestrator.process(document, _execution_context())

    assert document.items[0].events == ()


def test_process_handles_multiple_requests_independently():
    document = _parse(
        [
            {"name": "Criar", "id": "r1", "request": {"method": "POST", "url": "https://x/a"}},
            {"name": "Listar", "id": "r2", "request": {"method": "GET", "url": "https://x/b"}},
        ]
    )
    orchestrator = _build_orchestrator()

    result = orchestrator.process(document, _execution_context())

    assert {o.endpoint_source for o in result.endpoint_outcomes} == {"POST /a", "GET /b"}


def test_process_result_is_deterministic():
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
    orchestrator = _build_orchestrator()

    first = orchestrator.process(document, _execution_context(id_factory=lambda: "exec-a"))
    second = orchestrator.process(document, _execution_context(id_factory=lambda: "exec-b"))

    assert (
        first.endpoint_outcomes[0].generated_script.script
        == second.endpoint_outcomes[0].generated_script.script
    )
    assert first.diff.entries == second.diff.entries
