import json
from dataclasses import dataclass

from api_quality_agent.application.orchestration import CollectionGenerationResult
from api_quality_agent.domain.exceptions import (
    InputError,
    IntegrationError,
    UpdateNotApprovedError,
)
from api_quality_agent.domain.models import (
    ApprovalResult,
    ArtifactLocation,
    DiffResult,
    ExecutionContext,
    GeneratedArtifact,
)
from api_quality_agent.domain.policies import ensure_non_empty_id
from api_quality_agent.domain.services import ApprovalPolicy
from api_quality_agent.parsers import PostmanCollectionSerializer
from api_quality_agent.ports.outbound import ArtifactRepository, CollectionRepository

BACKUP_CATEGORY = "backups"
BACKUP_FILENAME = "original_collection.json"


@dataclass(frozen=True)
class CollectionUpdateResult:
    execution_context: ExecutionContext
    collection_id: str
    confirmed_collection_id: str
    approval: ApprovalResult
    diff: DiffResult
    backup_location: ArtifactLocation | None


class UpdateCollectionUseCase:
    def __init__(
        self,
        collection_repository: CollectionRepository,
        artifact_repository: ArtifactRepository,
        *,
        collection_serializer: PostmanCollectionSerializer | None = None,
    ) -> None:
        self._collection_repository = collection_repository
        self._artifact_repository = artifact_repository
        self._collection_serializer = collection_serializer or PostmanCollectionSerializer()

    def execute(
        self,
        generation_result: CollectionGenerationResult,
        approval_policy: ApprovalPolicy,
        *,
        create_backup: bool = True,
    ) -> CollectionUpdateResult:
        execution_context = generation_result.execution_context
        collection_id_value = execution_context.collection_id
        if collection_id_value is None:
            raise InputError(
                "O resultado de geração não possui uma Collection selecionada; "
                "impossível atualizar."
            )
        collection_id = ensure_non_empty_id(collection_id_value, "collection_id")

        approval = approval_policy.evaluate(generation_result.diff)
        if not approval.approved:
            raise UpdateNotApprovedError(approval.reason)

        backup_location: ArtifactLocation | None = None
        if create_backup:
            backup_location = self._save_backup(generation_result, collection_id=collection_id)

        # A Collection só pode ser atualizada pelo ID já validado acima — nunca
        # por nome — e o corpo enviado é exatamente generation_result.modified_document,
        # o mesmo documento já aprovado via diff (scripts manuais preservados,
        # sem regeneração nesta etapa).
        confirmed_id = self._collection_repository.update(
            collection_id, generation_result.modified_document
        )

        if confirmed_id != collection_id:
            raise IntegrationError(
                "A API do Postman confirmou a atualização de uma Collection diferente da "
                "selecionada; nenhuma ação adicional foi realizada."
            )

        return CollectionUpdateResult(
            execution_context=execution_context,
            collection_id=collection_id,
            confirmed_collection_id=confirmed_id,
            approval=approval,
            diff=generation_result.diff,
            backup_location=backup_location,
        )

    def _save_backup(
        self, generation_result: CollectionGenerationResult, *, collection_id: str
    ) -> ArtifactLocation:
        execution_context = generation_result.execution_context
        workspace_id_value = execution_context.workspace_id
        if workspace_id_value is None:
            raise InputError(
                "O resultado de geração não possui um Workspace associado; "
                "impossível salvar o backup."
            )
        workspace_id = ensure_non_empty_id(workspace_id_value, "workspace_id")

        serialized = self._collection_serializer.serialize(generation_result.original_document)
        artifact = GeneratedArtifact(
            category=BACKUP_CATEGORY,
            relative_path=BACKUP_FILENAME,
            content=json.dumps({"collection": serialized}, indent=2, ensure_ascii=False),
        )
        return self._artifact_repository.save(
            workspace_id=workspace_id,
            collection_id=collection_id,
            execution_id=execution_context.execution_id,
            artifact=artifact,
        )
