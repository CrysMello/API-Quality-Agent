"""Cenários 1, 2 e 20 do MVP: modo offline (sem acesso à rede) e
independência entre uma falha do Postman e o fluxo offline.
"""

import pytest
from conftest import FIXTURES_DIR

from api_quality_agent.adapters.filesystem import InputResolver
from api_quality_agent.adapters.postman import PostmanApiClient, PostmanWorkspaceRepository
from api_quality_agent.application.orchestration import AgentOrchestrator
from api_quality_agent.application.use_cases import ListWorkspacesUseCase
from api_quality_agent.domain.exceptions import AuthenticationError
from api_quality_agent.domain.models import ExecutionContext, ExecutionMode
from api_quality_agent.domain.services import (
    ApiAnalysisEngine,
    DiffEngine,
    ManagedBlockMerger,
    SchemaInferenceEngine,
    TestStrategyEngine,
)
from api_quality_agent.generators import PostmanTestGenerator
from api_quality_agent.parsers import OpenApiParser, PostmanCollectionParser


def _build_orchestrator() -> AgentOrchestrator:
    return AgentOrchestrator(
        ApiAnalysisEngine(),
        SchemaInferenceEngine(),
        TestStrategyEngine(),
        PostmanTestGenerator(),
        ManagedBlockMerger(),
        DiffEngine(),
    )


# --- Cenário 1: modo offline com JSON (Collection Postman local) -----------------------


def test_scenario_01_offline_mode_with_local_collection_json():
    resolved = InputResolver().resolve_from_file(FIXTURES_DIR / "offline_collection.json")
    document = PostmanCollectionParser().parse(resolved)

    execution_context = ExecutionContext.create(
        mode=ExecutionMode.OFFLINE,
        source="local-file",
        id_factory=lambda: "exec-offline-json",
    )

    result = _build_orchestrator().process(document, execution_context)

    assert execution_context.mode == ExecutionMode.OFFLINE
    assert len(result.endpoint_outcomes) == 2
    assert all(outcome.error is None for outcome in result.endpoint_outcomes)
    assert all(outcome.generated_script is not None for outcome in result.endpoint_outcomes)


# --- Cenário 2: modo offline com OpenAPI -------------------------------------------------


def test_scenario_02_offline_mode_with_openapi_spec():
    resolved = InputResolver().resolve_from_file(FIXTURES_DIR / "offline_openapi.json")
    specification = OpenApiParser().parse(resolved)

    result = ApiAnalysisEngine().analyze(specification)

    assert result.source_type == specification.spec_type.value
    sources = {endpoint.source for endpoint in result.endpoints}
    assert sources == {"GET /pets", "POST /pets", "GET /pets/{petId}"}


# --- Cenário 20: falha do Postman não impede o modo offline -----------------------------


def test_scenario_20_postman_failure_does_not_block_offline_mode(postman_test_server):
    postman_test_server.set_route(
        "/workspaces", status=401, body={"error": {"message": "invalid key"}}
    )
    client = PostmanApiClient("fake-key", base_url=postman_test_server.base_url, max_retries=0)
    workspace_repository = PostmanWorkspaceRepository(client)

    # 1. O caminho online falha com o erro correto...
    with pytest.raises(AuthenticationError):
        ListWorkspacesUseCase(workspace_repository).execute()

    # 2. ...mas isso não afeta, no mesmo processo, o fluxo totalmente offline.
    resolved = InputResolver().resolve_from_file(FIXTURES_DIR / "offline_collection.json")
    document = PostmanCollectionParser().parse(resolved)
    execution_context = ExecutionContext.create(
        mode=ExecutionMode.OFFLINE,
        source="local-file",
        id_factory=lambda: "exec-offline-after-failure",
    )
    result = _build_orchestrator().process(document, execution_context)

    assert len(result.endpoint_outcomes) == 2
    assert all(outcome.error is None for outcome in result.endpoint_outcomes)
