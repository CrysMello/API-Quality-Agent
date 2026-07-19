import os
from dataclasses import dataclass

from api_quality_agent.adapters.config import FileSelectionRepository
from api_quality_agent.adapters.filesystem import LocalArtifactRepository
from api_quality_agent.adapters.postman import (
    PostmanApiClient,
    PostmanCollectionRepository,
    PostmanWorkspaceRepository,
)
from api_quality_agent.application.orchestration import AgentOrchestrator
from api_quality_agent.application.use_cases import (
    GenerateCollectionTestsUseCase,
    GetCurrentWorkspaceUseCase,
    ListCollectionsUseCase,
    ResolveCollectionUseCase,
)
from api_quality_agent.domain.exceptions import ConfigurationError, InputError, ResourceNotFoundError
from api_quality_agent.domain.models import CollectionRef, WorkspaceRef
from api_quality_agent.domain.services import (
    ApiAnalysisEngine,
    CollectionSelectionService,
    DiffEngine,
    ManagedBlockMerger,
    SchemaInferenceEngine,
    TestStrategyEngine,
)
from api_quality_agent.generators import PostmanTestGenerator
from api_quality_agent.ports.outbound import (
    ArtifactRepository,
    CollectionRepository,
    SelectionRepository,
    WorkspaceRepository,
)

POSTMAN_API_KEY_ENV_VAR = "POSTMAN_API_KEY"


@dataclass
class CliContext:
    # Composição de dependências da CLI (equivalente à build_app() usada nos
    # testes de aceitação) — a CLI só monta e invoca os use cases já
    # existentes; nenhuma regra de negócio nova vive aqui.
    workspace_repository: WorkspaceRepository
    collection_repository: CollectionRepository
    selection_repository: SelectionRepository
    selection_service: CollectionSelectionService
    get_current_workspace_use_case: GetCurrentWorkspaceUseCase
    resolve_collection_use_case: ResolveCollectionUseCase
    list_collections_use_case: ListCollectionsUseCase
    generate_use_case: GenerateCollectionTestsUseCase


def build_context(
    *,
    artifact_repository: ArtifactRepository | None = None,
    selection_repository: SelectionRepository | None = None,
) -> CliContext:
    api_key = os.environ.get(POSTMAN_API_KEY_ENV_VAR)
    if not api_key:
        raise ConfigurationError(
            f"A variável de ambiente {POSTMAN_API_KEY_ENV_VAR} não está configurada. "
            "Defina-a antes de usar comandos que acessam a API do Postman."
        )

    client = PostmanApiClient(api_key)
    workspace_repository: WorkspaceRepository = PostmanWorkspaceRepository(client)
    collection_repository: CollectionRepository = PostmanCollectionRepository(client)
    effective_selection_repository: SelectionRepository = (
        selection_repository or FileSelectionRepository()
    )
    selection_service = CollectionSelectionService(collection_repository)
    resolve_collection_use_case = ResolveCollectionUseCase(
        selection_service, collection_repository, effective_selection_repository
    )
    get_current_workspace_use_case = GetCurrentWorkspaceUseCase(effective_selection_repository)

    orchestrator = AgentOrchestrator(
        ApiAnalysisEngine(),
        SchemaInferenceEngine(),
        TestStrategyEngine(),
        PostmanTestGenerator(),
        ManagedBlockMerger(),
        DiffEngine(),
    )
    generate_use_case = GenerateCollectionTestsUseCase(
        get_current_workspace_use_case,
        resolve_collection_use_case,
        collection_repository,
        orchestrator,
        artifact_repository or LocalArtifactRepository(),
    )

    return CliContext(
        workspace_repository=workspace_repository,
        collection_repository=collection_repository,
        selection_repository=effective_selection_repository,
        selection_service=selection_service,
        get_current_workspace_use_case=get_current_workspace_use_case,
        resolve_collection_use_case=resolve_collection_use_case,
        list_collections_use_case=ListCollectionsUseCase(
            collection_repository, effective_selection_repository
        ),
        generate_use_case=generate_use_case,
    )


def resolve_active_workspace(context: CliContext) -> WorkspaceRef:
    workspace_id = context.get_current_workspace_use_case.execute()
    if not workspace_id:
        raise InputError(
            "Nenhum Workspace ativo configurado. Selecione um Workspace antes de "
            "usar este comando."
        )
    workspaces = context.workspace_repository.list()
    match = next((workspace for workspace in workspaces if workspace.id == workspace_id), None)
    if match is None:
        raise ResourceNotFoundError(
            f"O Workspace ativo configurado (ID '{workspace_id}') não foi encontrado "
            "ou não está mais acessível com a API Key atual."
        )
    return match


def sort_collections(collections: tuple[CollectionRef, ...]) -> list[CollectionRef]:
    # Ordenação estável e determinística, documentada: nome (alfabético) com
    # o ID como critério de desempate. Só é válida para a listagem da
    # execução atual — o índice nunca deve ser tratado como identificador
    # persistente entre chamadas.
    return sorted(collections, key=lambda collection: (collection.name, collection.id))
