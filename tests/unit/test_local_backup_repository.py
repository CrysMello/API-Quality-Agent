import hashlib
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import api_quality_agent.adapters.filesystem.local_backup_repository as backup_module
from api_quality_agent.adapters.filesystem import LocalBackupRepository, verify_backup_integrity
from api_quality_agent.domain.exceptions import BackupError
from api_quality_agent.domain.models import BackupPolicy
from api_quality_agent.domain.policies import sanitize_path_segment


_FIXED_MOMENT = datetime(2026, 7, 18, 22, 15, 30, tzinfo=timezone.utc)


def _freeze_time(monkeypatch, moment: datetime = _FIXED_MOMENT) -> None:
    fixed_cls = type("_FrozenDatetime", (datetime,), {})
    fixed_cls.now = classmethod(lambda cls, tz=None: moment)
    monkeypatch.setattr(backup_module, "datetime", fixed_cls)


# --- Sanitização de caminho -----------------------------------------------------------


def test_sanitize_path_segment_blocks_path_traversal():
    assert ".." not in sanitize_path_segment("../../etc/passwd")
    assert "/" not in sanitize_path_segment("../../etc/passwd")


def test_sanitize_path_segment_falls_back_when_empty_or_none():
    assert sanitize_path_segment(None, fallback="default") == "default"
    assert sanitize_path_segment("   ", fallback="default") == "default"


# --- Backup integral e nome único -------------------------------------------------------


def test_save_preserves_content_exactly(tmp_path):
    repository = LocalBackupRepository(tmp_path)
    content = b'{"collection": {"auth": {"type": "bearer", "bearer": [{"value": "secret"}]}}}'

    metadata = repository.save(
        collection_id="c1", workspace_id="ws-1", content=content, contains_sensitive_data=True
    )

    assert metadata.backup_path.read_bytes() == content
    assert metadata.contains_sensitive_data is True


def test_save_uses_unique_timestamped_hashed_filename(tmp_path):
    repository = LocalBackupRepository(tmp_path)

    metadata = repository.save(
        collection_id="c1", workspace_id="ws-1", content=b"{}", contains_sensitive_data=True
    )

    name = metadata.backup_path.name
    assert name.endswith("_original_collection.json")
    timestamp_part = name.split("_")[0]
    assert len(timestamp_part) == 22  # YYYYMMDDTHHMMSSffffffZ (microssegundos)
    datetime.strptime(timestamp_part, "%Y%m%dT%H%M%S%fZ")  # não lança


def test_save_sanitizes_workspace_and_collection_ids_and_blocks_traversal(tmp_path):
    repository = LocalBackupRepository(tmp_path)

    metadata = repository.save(
        collection_id="../../etc/passwd",
        workspace_id="../../../root",
        content=b"{}",
        contains_sensitive_data=True,
    )

    resolved_base = tmp_path.resolve()
    resolved_backup = metadata.backup_path.resolve()
    assert resolved_base in resolved_backup.parents


def test_save_uses_default_directory_when_workspace_id_is_none(tmp_path):
    repository = LocalBackupRepository(tmp_path)

    metadata = repository.save(
        collection_id="c1", workspace_id=None, content=b"{}", contains_sensitive_data=True
    )

    assert (tmp_path / "default" / "c1") in metadata.backup_path.parents


def test_save_does_not_silently_overwrite_existing_backup(tmp_path, monkeypatch):
    _freeze_time(monkeypatch)
    repository = LocalBackupRepository(tmp_path)
    repository.save(collection_id="c1", workspace_id="ws-1", content=b"{}", contains_sensitive_data=True)

    with pytest.raises(BackupError):
        repository.save(
            collection_id="c1", workspace_id="ws-1", content=b"{}", contains_sensitive_data=True
        )


# --- Escrita atômica ---------------------------------------------------------------------


def test_save_leaves_no_temp_file_when_replace_fails(tmp_path, monkeypatch):
    repository = LocalBackupRepository(tmp_path)

    def _boom(_src, _dst):
        raise OSError("falha simulada de renomeação")

    monkeypatch.setattr(backup_module.os, "replace", _boom)

    with pytest.raises(OSError):
        repository.save(
            collection_id="c1", workspace_id="ws-1", content=b"{}", contains_sensitive_data=True
        )

    leftover = list((tmp_path / "ws-1" / "c1").glob(".tmp-backup-*"))
    assert leftover == []
    assert list((tmp_path / "ws-1" / "c1").glob("*_original_collection.json")) == []


# --- Hash e verificação de integridade ----------------------------------------------------


def test_save_computes_correct_sha256(tmp_path):
    repository = LocalBackupRepository(tmp_path)
    content = b'{"collection": {"info": {"name": "Col"}}}'

    metadata = repository.save(
        collection_id="c1", workspace_id="ws-1", content=content, contains_sensitive_data=True
    )

    assert metadata.sha256 == hashlib.sha256(content).hexdigest()
    assert metadata.size_bytes == len(content)


def test_verify_backup_integrity_succeeds_for_unmodified_file(tmp_path):
    repository = LocalBackupRepository(tmp_path)
    metadata = repository.save(
        collection_id="c1", workspace_id="ws-1", content=b"{}", contains_sensitive_data=True
    )

    assert verify_backup_integrity(metadata.backup_path, metadata.sha256) is True


def test_verify_backup_integrity_detects_corrupted_file(tmp_path):
    repository = LocalBackupRepository(tmp_path)
    metadata = repository.save(
        collection_id="c1", workspace_id="ws-1", content=b"{}", contains_sensitive_data=True
    )

    with open(metadata.backup_path, "ab") as handle:
        handle.write(b"tampered")

    assert verify_backup_integrity(metadata.backup_path, metadata.sha256) is False


def test_verify_backup_integrity_returns_false_for_missing_file(tmp_path):
    assert verify_backup_integrity(tmp_path / "does" / "not" / "exist.json", "abc") is False


def test_repository_verify_method_matches_free_function(tmp_path):
    repository = LocalBackupRepository(tmp_path)
    metadata = repository.save(
        collection_id="c1", workspace_id="ws-1", content=b"{}", contains_sensitive_data=True
    )

    assert repository.verify(metadata.backup_path, metadata.sha256) is True
    assert repository.verify(metadata.backup_path, "0" * 64) is False


# --- Retenção -----------------------------------------------------------------------------


def _write_backup_file(directory: Path, *, moment: datetime, content: bytes = b"{}") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(content + moment.isoformat().encode()).hexdigest()[:8]
    name = f"{moment.strftime('%Y%m%dT%H%M%S%fZ')}_{digest}_original_collection.json"
    path = directory / name
    path.write_bytes(content)
    return path


def test_retention_disabled_removes_nothing(tmp_path):
    repository = LocalBackupRepository(tmp_path)
    target_dir = tmp_path / "ws-1" / "c1"
    old = _write_backup_file(target_dir, moment=datetime.now(timezone.utc) - timedelta(days=30))

    repository.apply_retention(
        collection_id="c1",
        workspace_id="ws-1",
        policy=BackupPolicy(enabled=False, directory=tmp_path),
        keep_path=old,
    )

    assert old.exists()


def test_retention_keeps_only_configured_max_backups(tmp_path):
    repository = LocalBackupRepository(tmp_path)
    target_dir = tmp_path / "ws-1" / "c1"
    now = datetime.now(timezone.utc)
    oldest = _write_backup_file(target_dir, moment=now - timedelta(hours=3))
    middle = _write_backup_file(target_dir, moment=now - timedelta(hours=2))
    newest_old = _write_backup_file(target_dir, moment=now - timedelta(hours=1))
    just_created = _write_backup_file(target_dir, moment=now)

    repository.apply_retention(
        collection_id="c1",
        workspace_id="ws-1",
        policy=BackupPolicy(enabled=True, directory=tmp_path, max_backups_per_collection=2),
        keep_path=just_created,
    )

    assert not oldest.exists()
    assert not middle.exists()
    assert newest_old.exists()
    assert just_created.exists()


def test_retention_removes_backups_older_than_max_age(tmp_path):
    repository = LocalBackupRepository(tmp_path)
    target_dir = tmp_path / "ws-1" / "c1"
    now = datetime.now(timezone.utc)
    old = _write_backup_file(target_dir, moment=now - timedelta(days=10))
    recent = _write_backup_file(target_dir, moment=now - timedelta(hours=1))

    repository.apply_retention(
        collection_id="c1",
        workspace_id="ws-1",
        policy=BackupPolicy(enabled=True, directory=tmp_path, max_age_days=5),
        keep_path=recent,
    )

    assert not old.exists()
    assert recent.exists()


def test_retention_never_deletes_the_just_created_backup_even_if_oldest(tmp_path):
    repository = LocalBackupRepository(tmp_path)
    target_dir = tmp_path / "ws-1" / "c1"
    now = datetime.now(timezone.utc)
    # o "recém-criado" tem timestamp mais antigo que os demais candidatos de propósito
    just_created = _write_backup_file(target_dir, moment=now - timedelta(days=100))
    _write_backup_file(target_dir, moment=now)

    repository.apply_retention(
        collection_id="c1",
        workspace_id="ws-1",
        policy=BackupPolicy(enabled=True, directory=tmp_path, max_backups_per_collection=1),
        keep_path=just_created,
    )

    assert just_created.exists()


def test_retention_never_deletes_files_outside_backup_naming_pattern(tmp_path):
    repository = LocalBackupRepository(tmp_path)
    target_dir = tmp_path / "ws-1" / "c1"
    target_dir.mkdir(parents=True)
    unrelated = target_dir / "notas.txt"
    unrelated.write_text("não é um backup")
    just_created = _write_backup_file(target_dir, moment=datetime.now(timezone.utc))

    repository.apply_retention(
        collection_id="c1",
        workspace_id="ws-1",
        policy=BackupPolicy(enabled=True, directory=tmp_path, max_backups_per_collection=0),
        keep_path=just_created,
    )

    assert unrelated.exists()


def test_retention_does_not_follow_symlinks(tmp_path):
    repository = LocalBackupRepository(tmp_path)
    target_dir = tmp_path / "ws-1" / "c1"
    target_dir.mkdir(parents=True)
    outside_target = tmp_path / "outside_secret.json"
    outside_target.write_text("fora do diretório de backups")
    symlink_path = target_dir / "20200101T000000000000Z_aaaaaaaa_original_collection.json"
    try:
        symlink_path.symlink_to(outside_target)
    except (OSError, NotImplementedError):
        pytest.skip("Criação de symlink não suportada/permitida neste ambiente.")

    just_created = _write_backup_file(target_dir, moment=datetime.now(timezone.utc))

    repository.apply_retention(
        collection_id="c1",
        workspace_id="ws-1",
        policy=BackupPolicy(enabled=True, directory=tmp_path, max_backups_per_collection=1),
        keep_path=just_created,
    )

    assert outside_target.exists()
    assert outside_target.read_text() == "fora do diretório de backups"


def test_retention_failure_logs_warning_and_preserves_just_created_backup(tmp_path, monkeypatch, caplog):
    repository = LocalBackupRepository(tmp_path)
    target_dir = tmp_path / "ws-1" / "c1"
    now = datetime.now(timezone.utc)
    old = _write_backup_file(target_dir, moment=now - timedelta(days=30))
    just_created = _write_backup_file(target_dir, moment=now)

    def _boom(_self):
        raise OSError("permissão negada (simulado)")

    monkeypatch.setattr(Path, "unlink", _boom)

    with caplog.at_level(logging.WARNING):
        repository.apply_retention(
            collection_id="c1",
            workspace_id="ws-1",
            policy=BackupPolicy(enabled=True, directory=tmp_path, max_backups_per_collection=1),
            keep_path=just_created,
        )

    assert just_created.exists()
    assert any("retenção" in record.message for record in caplog.records)
    assert old.exists()  # unlink falhou (simulado), então o arquivo permanece


# --- Proteção contra Git --------------------------------------------------------------------


_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_gitignore_covers_backup_artifacts():
    gitignore_content = (_REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "backups/" in gitignore_content
    assert "*.backup.json" in gitignore_content
    assert "*_original_collection.json" in gitignore_content


def test_save_warns_when_git_protection_cannot_be_confirmed(tmp_path, caplog):
    # tmp_path fica fora do repositório Git do projeto: git check-ignore não
    # confirma proteção, então um warning seguro (sem conteúdo do backup)
    # deve ser emitido.
    repository = LocalBackupRepository(tmp_path)

    with caplog.at_level(logging.WARNING):
        metadata = repository.save(
            collection_id="c1", workspace_id="ws-1", content=b"{}", contains_sensitive_data=True
        )

    warning_messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "gitignore" in warning_messages.lower() or "git" in warning_messages.lower()
    assert str(metadata.backup_path.read_bytes()) not in warning_messages
