import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from api_quality_agent.application.orchestration import CollectionGenerationResult
from api_quality_agent.domain.exceptions import (
    BackupIntegrityError,
    InputError,
    IntegrationError,
    UpdateNotApprovedError,
)
from api_quality_agent.domain.models import BackupMetadata, BackupPolicy, PostmanCollectionDocument
from api_quality_agent.domain.policies import ensure_non_empty_id
from api_quality_agent.domain.services import ApprovalPolicy
from api_quality_agent.parsers import PostmanCollectionSerializer
from api_quality_agent.ports.outbound import BackupRepository, CollectionRepository

logger = logging.getLogger(__name__)

DEFAULT_BACKUP_POLICY = BackupPolicy(enabled=True, directory=Path("backups"))


@dataclass(frozen=True)
class CollectionUpdateResult:
    # Somente metadados seguros: nunca o documento, o backup, o payload
    # enviado, headers HTTP completos, a resposta completa da API ou a API Key.
    collection_id: str
    updated: bool
    dry_run: bool
    backup_created: bool
    backup_path: Path | None
    backup_sha256: str | None
    request_id: str | None
    status_code: int | None
    document_hash: str


class UpdateCollectionUseCase:
    def __init__(
        self,
        collection_repository: CollectionRepository,
        backup_repository: BackupRepository,
        *,
        collection_serializer: PostmanCollectionSerializer | None = None,
    ) -> None:
        self._collection_repository = collection_repository
        self._backup_repository = backup_repository
        self._collection_serializer = collection_serializer or PostmanCollectionSerializer()

    def execute(
        self,
        generation_result: CollectionGenerationResult,
        approval_policy: ApprovalPolicy,
        *,
        backup_policy: BackupPolicy | None = None,
    ) -> CollectionUpdateResult:
        backup_policy = backup_policy or DEFAULT_BACKUP_POLICY
        execution_context = generation_result.execution_context

        # 2. Validar Collection ID — único identificador usado a partir daqui;
        # nunca por nome, nunca obtido de outra fonte além do próprio
        # resultado de geração já validado na etapa anterior.
        collection_id = self._require_collection_id(execution_context.collection_id)
        document_hash = _hash_document(generation_result.modified_document, self._collection_serializer)

        # 3. Validar diff — nada a enviar quando não há mudanças. Isso também
        # cobre dry-run com diff vazio: a ApprovalPolicy aprovaria por não
        # haver "has_changes", mas não existe nenhuma ação real a aplicar.
        if not generation_result.diff.has_changes:
            logger.info(
                "Collection update skipped (no changes): collection_id=%s document_sha256=%s",
                collection_id,
                document_hash,
            )
            return CollectionUpdateResult(
                collection_id=collection_id,
                updated=False,
                dry_run=approval_policy.dry_run,
                backup_created=False,
                backup_path=None,
                backup_sha256=None,
                request_id=None,
                status_code=None,
                document_hash=document_hash,
            )

        # 4/5. Validar ApprovalResult — a ApprovalPolicy já trata dry-run como
        # bloqueio absoluto sempre que há mudanças reais a aplicar (o caso de
        # dry-run sem mudanças já foi resolvido no passo anterior).
        approval = approval_policy.evaluate(generation_result.diff)
        if not approval.approved:
            logger.info(
                "Collection update denied: collection_id=%s dry_run=%s",
                collection_id,
                approval_policy.dry_run,
            )
            raise UpdateNotApprovedError(approval.reason)

        # 6. Criar backup local da versão original, quando habilitado.
        backup_metadata: BackupMetadata | None = None
        if backup_policy.enabled:
            backup_metadata = self._create_backup(generation_result, collection_id=collection_id)
            # 7. Verificar integridade do backup antes de prosseguir.
            if not self._backup_repository.verify(
                backup_metadata.backup_path, backup_metadata.sha256
            ):
                raise BackupIntegrityError(
                    "Falha na verificação de integridade do backup local; a atualização "
                    "remota foi interrompida por segurança."
                )

        # 8. Atualizar somente a Collection selecionada (nunca por nome, nunca
        # todas as Collections do Workspace).
        receipt = self._collection_repository.update(
            collection_id, generation_result.modified_document
        )

        # 9. Validar resposta da API.
        if receipt.confirmed_collection_id != collection_id:
            raise IntegrationError(
                "A API do Postman confirmou a atualização de uma Collection diferente da "
                "selecionada; nenhuma ação adicional foi realizada."
            )

        # 10. Aplicar retenção — somente após backup válido e atualização confirmada.
        if backup_metadata is not None:
            self._apply_retention(
                collection_id=collection_id,
                workspace_id=execution_context.workspace_id,
                policy=backup_policy,
                keep_path=backup_metadata.backup_path,
            )

        # 11. Registrar somente metadados seguros (nunca a Collection completa,
        # o backup, o payload enviado ou a resposta completa da API).
        logger.info(
            "Collection update completed: collection_id=%s status=%s document_sha256=%s "
            "backup_created=%s",
            collection_id,
            receipt.status_code,
            receipt.document_hash,
            backup_metadata is not None,
        )

        # 12. Retornar CollectionUpdateResult.
        return CollectionUpdateResult(
            collection_id=collection_id,
            updated=True,
            dry_run=approval_policy.dry_run,
            backup_created=backup_metadata is not None,
            backup_path=backup_metadata.backup_path if backup_metadata is not None else None,
            backup_sha256=backup_metadata.sha256 if backup_metadata is not None else None,
            request_id=receipt.request_id,
            status_code=receipt.status_code,
            document_hash=receipt.document_hash,
        )

    @staticmethod
    def _require_collection_id(collection_id: str | None) -> str:
        if collection_id is None:
            raise InputError(
                "O resultado de geração não possui uma Collection selecionada; "
                "impossível atualizar."
            )
        return ensure_non_empty_id(collection_id, "collection_id")

    def _create_backup(
        self, generation_result: CollectionGenerationResult, *, collection_id: str
    ) -> BackupMetadata:
        serialized = self._collection_serializer.serialize(generation_result.original_document)
        content = json.dumps({"collection": serialized}, indent=2, ensure_ascii=False).encode(
            "utf-8"
        )
        # O backup preserva o documento ORIGINAL (pré-modificação), nunca o
        # documento já mesclado/atualizado — ver testes de "backup da versão
        # correta". auth/headers/tokens não são mascarados aqui: mascarar
        # tornaria o backup inútil para restauração; por isso é tratado como
        # artefato sensível (permissões restritas, fora de artifacts/,
        # protegido via .gitignore), nunca como conteúdo público.
        return self._backup_repository.save(
            collection_id=collection_id,
            workspace_id=generation_result.execution_context.workspace_id,
            content=content,
            contains_sensitive_data=True,
        )

    def _apply_retention(
        self, *, collection_id: str, workspace_id: str | None, policy: BackupPolicy, keep_path: Path
    ) -> None:
        try:
            self._backup_repository.apply_retention(
                collection_id=collection_id,
                workspace_id=workspace_id,
                policy=policy,
                keep_path=keep_path,
            )
        except Exception:
            # Falha na limpeza nunca pode comprometer uma atualização já
            # concluída com sucesso, nem o backup recém-criado.
            logger.warning(
                "Falha ao aplicar retenção de backups para collection_id=%s; "
                "a atualização já concluída não foi afetada.",
                collection_id,
            )


def _hash_document(
    document: PostmanCollectionDocument, serializer: PostmanCollectionSerializer
) -> str:
    # Mesma forma de serialização usada por PostmanCollectionRepository.update()
    # para o payload real, garantindo que o hash seja comparável entre os
    # caminhos "sem mudanças" e "atualização enviada".
    body = {"collection": serializer.serialize(document)}
    return hashlib.sha256(json.dumps(body).encode("utf-8")).hexdigest()
