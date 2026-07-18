import hashlib
import logging
import os
import re
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from api_quality_agent.domain.exceptions import BackupError
from api_quality_agent.domain.models import BackupMetadata, BackupPolicy
from api_quality_agent.domain.policies import sanitize_path_segment

logger = logging.getLogger(__name__)

DEFAULT_BACKUP_BASE_PATH = Path("backups")

_TIMESTAMP_FORMAT = "%Y%m%dT%H%M%S%fZ"
# Precisão de microssegundos (em vez de apenas segundos) evita colisões de
# nome entre backups legítimos e sucessivos do mesmo conteúdo — necessários
# para que reenvios idempotentes do mesmo documento continuem gerando um
# registro de auditoria próprio por execução, sem serem tratados como
# sobrescrita.
_BACKUP_FILENAME_PATTERN = re.compile(
    r"^(?P<timestamp>\d{8}T\d{12}Z)_(?P<hash>[0-9a-f]{8})_original_collection\.json$"
)


class LocalBackupRepository:
    # Backups vivem numa árvore própria (fora de artifacts/), pois representam
    # uma cópia integral e não mascarada da Collection original — tratado como
    # conteúdo sensível, nunca como artefato público (ver .gitignore).
    def __init__(self, base_path: Path | None = None) -> None:
        self._base_path = base_path or DEFAULT_BACKUP_BASE_PATH

    def save(
        self,
        *,
        collection_id: str,
        workspace_id: str | None,
        content: bytes,
        contains_sensitive_data: bool,
    ) -> BackupMetadata:
        target_dir = self._collection_directory(collection_id, workspace_id)
        target_dir.mkdir(parents=True, exist_ok=True)

        digest = hashlib.sha256(content).hexdigest()
        created_at = datetime.now(timezone.utc)
        filename = (
            f"{created_at.strftime(_TIMESTAMP_FORMAT)}_{digest[:8]}_original_collection.json"
        )
        final_path = target_dir / filename

        if final_path.exists():
            raise BackupError(
                "Já existe um backup com o mesmo nome no destino; a gravação foi "
                "interrompida para evitar sobrescrita silenciosa."
            )

        self._write_atomically(target_dir, final_path, content)
        self._apply_best_effort_permissions(final_path)
        self._warn_if_not_git_protected(final_path)

        return BackupMetadata(
            collection_id=collection_id,
            created_at_utc=created_at,
            sha256=digest,
            size_bytes=len(content),
            contains_sensitive_data=contains_sensitive_data,
            backup_path=final_path,
        )

    def verify(self, backup_path: Path, expected_sha256: str) -> bool:
        return verify_backup_integrity(backup_path, expected_sha256)

    def apply_retention(
        self,
        *,
        collection_id: str,
        workspace_id: str | None,
        policy: BackupPolicy,
        keep_path: Path,
    ) -> None:
        if not policy.enabled:
            return

        target_dir = (
            policy.directory
            / sanitize_path_segment(workspace_id, fallback="default")
            / sanitize_path_segment(collection_id)
        )
        if not target_dir.is_dir():
            return

        candidates = self._list_backup_candidates(target_dir, keep_path)
        to_delete = self._select_for_deletion(candidates, policy)

        for entry, _timestamp in to_delete:
            try:
                entry.unlink()
            except OSError:
                # Falha na limpeza não pode arriscar o backup recém-criado (que
                # nunca está em `to_delete`) nem interromper o fluxo principal.
                logger.warning(
                    "Falha ao aplicar retenção de backups para collection_id=%s; "
                    "arquivo mantido.",
                    collection_id,
                )

    def _collection_directory(self, collection_id: str, workspace_id: str | None) -> Path:
        return (
            self._base_path
            / sanitize_path_segment(workspace_id, fallback="default")
            / sanitize_path_segment(collection_id)
        )

    @staticmethod
    def _write_atomically(target_dir: Path, final_path: Path, content: bytes) -> None:
        fd, tmp_name = tempfile.mkstemp(dir=target_dir, prefix=".tmp-backup-", suffix=".part")
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as tmp_file:
                tmp_file.write(content)
                tmp_file.flush()
                try:
                    os.fsync(tmp_file.fileno())
                except OSError:
                    pass  # fsync não suportado neste sistema de arquivos: melhor esforço
            os.replace(tmp_path, final_path)
        except BaseException:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    @staticmethod
    def _apply_best_effort_permissions(path: Path) -> None:
        try:
            os.chmod(path, 0o600)
        except OSError:
            logger.warning(
                "Não foi possível restringir as permissões do arquivo de backup "
                "neste sistema operacional (melhor esforço); prosseguindo."
            )

    @staticmethod
    def _warn_if_not_git_protected(path: Path) -> None:
        try:
            result = subprocess.run(
                ["git", "check-ignore", "-q", str(path)],
                cwd=path.parent,
                capture_output=True,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            logger.warning(
                "Não foi possível confirmar via git se o diretório de backups está "
                "coberto pelo .gitignore (git indisponível ou fora de um repositório)."
            )
            return

        if result.returncode != 0:
            logger.warning(
                "O diretório de backups pode não estar protegido por .gitignore; "
                "verifique a configuração antes de versionar arquivos deste diretório."
            )

    @staticmethod
    def _list_backup_candidates(
        target_dir: Path, keep_path: Path
    ) -> list[tuple[Path, datetime]]:
        resolved_keep_path = keep_path.resolve()
        candidates: list[tuple[Path, datetime]] = []
        for entry in target_dir.iterdir():
            if entry.is_symlink():
                continue  # nunca seguir symlink para fora do diretório de backups
            if not entry.is_file():
                continue
            if entry.resolve() == resolved_keep_path:
                continue  # o backup recém-criado nunca é candidato à remoção
            match = _BACKUP_FILENAME_PATTERN.match(entry.name)
            if not match:
                continue  # nunca remover arquivos fora do padrão de backup conhecido
            try:
                timestamp = datetime.strptime(
                    match.group("timestamp"), _TIMESTAMP_FORMAT
                ).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            candidates.append((entry, timestamp))
        return candidates

    @staticmethod
    def _select_for_deletion(
        candidates: list[tuple[Path, datetime]], policy: BackupPolicy
    ) -> list[tuple[Path, datetime]]:
        ordered = sorted(candidates, key=lambda item: item[1])  # mais antigo primeiro
        to_delete: dict[Path, tuple[Path, datetime]] = {}

        if policy.max_age_days is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=policy.max_age_days)
            for entry, timestamp in ordered:
                if timestamp < cutoff:
                    to_delete[entry] = (entry, timestamp)

        if policy.max_backups_per_collection is not None:
            surviving = [item for item in ordered if item[0] not in to_delete]
            # -1: o backup recém-criado (fora de `candidates`) sempre ocupa uma vaga.
            allowed_old = max(policy.max_backups_per_collection - 1, 0)
            if len(surviving) > allowed_old:
                for entry, timestamp in surviving[: len(surviving) - allowed_old]:
                    to_delete[entry] = (entry, timestamp)

        return list(to_delete.values())


def verify_backup_integrity(path: Path, expected_sha256: str) -> bool:
    try:
        content = Path(path).read_bytes()
    except OSError:
        return False
    return hashlib.sha256(content).hexdigest() == expected_sha256
