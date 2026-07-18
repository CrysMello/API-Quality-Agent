import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from api_quality_agent.adapters.config import FileSelectionRepository
from api_quality_agent.adapters.filesystem import LocalArtifactRepository, LocalBackupRepository
from api_quality_agent.adapters.newman import NewmanAdapter
from api_quality_agent.adapters.postman import (
    PostmanApiClient,
    PostmanCollectionRepository,
    PostmanWorkspaceRepository,
)
from api_quality_agent.application.orchestration import AgentOrchestrator
from api_quality_agent.application.use_cases import (
    GenerateCollectionTestsUseCase,
    GetCurrentCollectionUseCase,
    GetCurrentWorkspaceUseCase,
    ListCollectionsUseCase,
    ListWorkspacesUseCase,
    ResolveCollectionUseCase,
    RunCollectionUseCase,
    SelectCollectionUseCase,
    SelectWorkspaceUseCase,
    UpdateCollectionUseCase,
)
from api_quality_agent.domain.services import (
    ApiAnalysisEngine,
    CollectionSelectionService,
    DiffEngine,
    ManagedBlockMerger,
    SchemaInferenceEngine,
    TestStrategyEngine,
)
from api_quality_agent.generators import PostmanTestGenerator
from api_quality_agent.reporting import ReportEngine

# Fixtures pequenas e legíveis: só o essencial para exercitar cada fluxo do
# SAD, nunca dados reais de conta/API Key.
FAKE_API_KEY = "PMAK-acceptance-fake-key-0000000000000000"

WORKSPACE_ID = "ws-1"
WORKSPACE_NAME = "QA Workspace"

COLLECTION_A_ID = "col-a"
COLLECTION_A_NAME = "Pets API"
COLLECTION_B_ID = "col-b"
COLLECTION_B_NAME = "Orders API"
DUPLICATE_COLLECTION_ID = "col-a-dup"

FAKE_NEWMAN_SCRIPT = Path(__file__).resolve().parent.parent / "fake_newman.py"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def make_client(server, *, api_key: str = FAKE_API_KEY, max_retries: int = 0) -> PostmanApiClient:
    return PostmanApiClient(
        api_key, base_url=server.base_url, timeout_seconds=2.0, max_retries=max_retries
    )


def collection_a_payload(*, with_manual_script: bool = False) -> dict:
    request: dict = {
        "name": "Criar pet",
        "id": "req-a1",
        "request": {"method": "POST", "url": "https://api.exemplo.com/pets"},
        "response": [{"name": "ok", "status": "Created", "code": 201, "header": [], "body": "{}"}],
    }
    if with_manual_script:
        request["event"] = [
            {
                "listen": "test",
                "script": {
                    "exec": ["// script manual do time", "console.log('preservar isto');"]
                },
            }
        ]
    return {
        "info": {
            "name": COLLECTION_A_NAME,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": [request],
    }


def collection_b_payload() -> dict:
    return {
        "info": {
            "name": COLLECTION_B_NAME,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": [
            {
                "name": "Listar pedidos",
                "id": "req-b1",
                "request": {"method": "GET", "url": "https://api.exemplo.com/orders"},
                "response": [
                    {"name": "ok", "status": "OK", "code": 200, "header": [], "body": "[]"}
                ],
            }
        ],
    }


def configure_server(
    server, *, with_manual_script_in_a: bool = False, duplicate_name: bool = False
) -> None:
    server.set_route("/me", status=200, body={"user": {"id": 1, "username": "qa"}})
    server.set_route(
        "/workspaces",
        status=200,
        body={"workspaces": [{"id": WORKSPACE_ID, "name": WORKSPACE_NAME}]},
    )

    collections = [
        {"id": COLLECTION_A_ID, "uid": COLLECTION_A_ID, "name": COLLECTION_A_NAME},
        {"id": COLLECTION_B_ID, "uid": COLLECTION_B_ID, "name": COLLECTION_B_NAME},
    ]
    if duplicate_name:
        collections.append(
            {"id": DUPLICATE_COLLECTION_ID, "uid": DUPLICATE_COLLECTION_ID, "name": COLLECTION_A_NAME}
        )
    server.set_route(
        f"/collections?workspace={WORKSPACE_ID}",
        status=200,
        body={"collections": collections},
    )

    server.set_route(
        f"/collections/{COLLECTION_A_ID}",
        status=200,
        body={"collection": collection_a_payload(with_manual_script=with_manual_script_in_a)},
    )
    server.set_route(
        f"/collections/{COLLECTION_B_ID}",
        status=200,
        body={"collection": collection_b_payload()},
    )
    if duplicate_name:
        server.set_route(
            f"/collections/{DUPLICATE_COLLECTION_ID}",
            status=200,
            body={"collection": collection_a_payload()},
        )


@dataclass
class AcceptanceApp:
    client: PostmanApiClient
    workspace_repository: PostmanWorkspaceRepository
    collection_repository: PostmanCollectionRepository
    selection_repository: FileSelectionRepository
    selection_service: CollectionSelectionService
    list_workspaces: ListWorkspacesUseCase
    select_workspace: SelectWorkspaceUseCase
    list_collections: ListCollectionsUseCase
    select_collection: SelectCollectionUseCase
    resolve_collection: ResolveCollectionUseCase
    get_current_workspace: GetCurrentWorkspaceUseCase
    get_current_collection: GetCurrentCollectionUseCase
    orchestrator: AgentOrchestrator
    artifact_repository: LocalArtifactRepository
    backup_repository: LocalBackupRepository
    generate_use_case: GenerateCollectionTestsUseCase
    update_use_case: UpdateCollectionUseCase
    collection_runner: NewmanAdapter
    run_use_case: RunCollectionUseCase
    report_engine: ReportEngine


def build_app(
    server, tmp_path: Path, *, id_factory: Callable[[], str] | None = None
) -> AcceptanceApp:
    # Toda a árvore de dependências é montada a partir de classes já
    # existentes (mesmo padrão que um futuro wiring de CLI usaria) — nenhuma
    # classe nova é criada aqui, só composição.
    client = make_client(server)
    workspace_repository = PostmanWorkspaceRepository(client)
    collection_repository = PostmanCollectionRepository(client)
    selection_repository = FileSelectionRepository(tmp_path / "selection.json")
    selection_service = CollectionSelectionService(collection_repository)
    resolve_collection = ResolveCollectionUseCase(
        selection_service, collection_repository, selection_repository
    )
    get_current_workspace = GetCurrentWorkspaceUseCase(selection_repository)

    orchestrator = AgentOrchestrator(
        ApiAnalysisEngine(),
        SchemaInferenceEngine(),
        TestStrategyEngine(),
        PostmanTestGenerator(),
        ManagedBlockMerger(),
        DiffEngine(),
    )
    artifact_repository = LocalArtifactRepository(tmp_path / "artifacts")
    backup_repository = LocalBackupRepository(tmp_path / "backups")

    generate_kwargs = {"id_factory": id_factory} if id_factory is not None else {}
    generate_use_case = GenerateCollectionTestsUseCase(
        get_current_workspace,
        resolve_collection,
        collection_repository,
        orchestrator,
        artifact_repository,
        **generate_kwargs,
    )
    update_use_case = UpdateCollectionUseCase(collection_repository, backup_repository)

    collection_runner = NewmanAdapter(
        newman_executable=sys.executable, command_prefix=(str(FAKE_NEWMAN_SCRIPT),)
    )
    run_use_case = RunCollectionUseCase(
        get_current_workspace, resolve_collection, collection_repository, collection_runner
    )

    return AcceptanceApp(
        client=client,
        workspace_repository=workspace_repository,
        collection_repository=collection_repository,
        selection_repository=selection_repository,
        selection_service=selection_service,
        list_workspaces=ListWorkspacesUseCase(workspace_repository),
        select_workspace=SelectWorkspaceUseCase(workspace_repository, selection_repository),
        list_collections=ListCollectionsUseCase(collection_repository, selection_repository),
        select_collection=SelectCollectionUseCase(selection_service, selection_repository),
        resolve_collection=resolve_collection,
        get_current_workspace=get_current_workspace,
        get_current_collection=GetCurrentCollectionUseCase(selection_repository),
        orchestrator=orchestrator,
        artifact_repository=artifact_repository,
        backup_repository=backup_repository,
        generate_use_case=generate_use_case,
        update_use_case=update_use_case,
        collection_runner=collection_runner,
        run_use_case=run_use_case,
        report_engine=ReportEngine(),
    )
