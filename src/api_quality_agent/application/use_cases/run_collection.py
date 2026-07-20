import json
import os
import tempfile

from api_quality_agent.application.use_cases.get_current_workspace import (
    GetCurrentWorkspaceUseCase,
)
from api_quality_agent.application.use_cases.resolve_collection import ResolveCollectionUseCase
from api_quality_agent.domain.exceptions import InputError
from api_quality_agent.domain.models import ExecutionResult
from api_quality_agent.domain.policies import ensure_non_empty_id
from api_quality_agent.parsers import PostmanCollectionSerializer
from api_quality_agent.ports.outbound import CollectionRepository, CollectionRunner
from api_quality_agent.ports.outbound.collection_runner import DEFAULT_RUN_TIMEOUT_SECONDS


class RunCollectionUseCase:
    def __init__(
        self,
        get_current_workspace_use_case: GetCurrentWorkspaceUseCase | None,
        resolve_collection_use_case: ResolveCollectionUseCase | None,
        collection_repository: CollectionRepository | None,
        collection_runner: CollectionRunner,
        *,
        collection_serializer: PostmanCollectionSerializer | None = None,
    ) -> None:
        # Os três primeiros parâmetros só são necessários para o caminho
        # "Collection selecionada" (Workspace/Postman); execute(local_collection_path=...)
        # nunca os utiliza, o que permite montar este use case num contexto
        # puramente local (sem POSTMAN_API_KEY) — ver bootstrap.build_offline_run_context().
        self._get_current_workspace_use_case = get_current_workspace_use_case
        self._resolve_collection_use_case = resolve_collection_use_case
        self._collection_repository = collection_repository
        self._collection_runner = collection_runner
        self._collection_serializer = collection_serializer or PostmanCollectionSerializer()

    def execute(
        self,
        *,
        local_collection_path: str | None = None,
        collection_id: str | None = None,
        collection_name: str | None = None,
        environment_path: str | None = None,
        timeout_seconds: float = DEFAULT_RUN_TIMEOUT_SECONDS,
    ) -> ExecutionResult:
        # Environment é sempre opcional e nunca resolvido implicitamente: só é
        # usado quando explicitamente informado por quem chama.
        if environment_path is not None:
            ensure_non_empty_id(environment_path, "environment_path")

        if local_collection_path is not None:
            # Artefato local já gerado: executa diretamente, sem tocar
            # Workspace/Collection/seleção.
            resolved_path = ensure_non_empty_id(local_collection_path, "local_collection_path")
            return self._collection_runner.run(
                collection_path=resolved_path,
                environment_path=environment_path,
                timeout_seconds=timeout_seconds,
            )

        return self._execute_selected_collection(
            collection_id=collection_id,
            collection_name=collection_name,
            environment_path=environment_path,
            timeout_seconds=timeout_seconds,
        )

    def _execute_selected_collection(
        self,
        *,
        collection_id: str | None,
        collection_name: str | None,
        environment_path: str | None,
        timeout_seconds: float,
    ) -> ExecutionResult:
        if (
            self._get_current_workspace_use_case is None
            or self._resolve_collection_use_case is None
            or self._collection_repository is None
        ):
            raise InputError(
                "Este use case foi montado apenas para execução local "
                "(local_collection_path); informe local_collection_path ou "
                "monte-o com as dependências de Workspace/Postman."
            )

        workspace_id = self._get_current_workspace_use_case.execute()
        if not workspace_id:
            raise InputError(
                "Nenhum Workspace ativo. Selecione um Workspace antes de executar."
            )

        # collection_id/collection_name aqui representam uma seleção temporária:
        # ResolveCollectionUseCase nunca persiste a partir desses overrides.
        collection_ref = self._resolve_collection_use_case.execute(
            collection_id=collection_id, collection_name=collection_name
        )

        # Somente a Collection selecionada é obtida — nunca todas do Workspace.
        document = self._collection_repository.get(collection_ref.id)
        serialized = {"collection": self._collection_serializer.serialize(document)}

        tmp_path = _write_temp_collection_file(serialized)
        try:
            return self._collection_runner.run(
                collection_path=tmp_path,
                environment_path=environment_path,
                timeout_seconds=timeout_seconds,
            )
        finally:
            _remove_file_quietly(tmp_path)


def _write_temp_collection_file(serialized_collection: dict) -> str:
    fd, path = tempfile.mkstemp(prefix="api-quality-agent-run-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(serialized_collection, handle)
    except BaseException:
        _remove_file_quietly(path)
        raise
    return path


def _remove_file_quietly(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass
