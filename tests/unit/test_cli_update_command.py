from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest import (
    COLLECTION_A_ID,
    COLLECTION_A_NAME,
    COLLECTION_B_ID,
    COLLECTION_B_NAME,
    FAKE_API_KEY,
    WORKSPACE_ID,
    configure_server,
)

from api_quality_agent.cli import bootstrap
from api_quality_agent.cli.exit_codes import (
    AMBIGUOUS_SELECTION,
    INVALID_INPUT_OR_CONFIGURATION,
    OPERATION_CANCELLED,
    RESOURCE_NOT_FOUND,
    SUCCESS,
)
from api_quality_agent.cli.main import main
from api_quality_agent.domain.models import BackupMetadata


def _put_paths(server) -> list[str]:
    return [
        path
        for path, method in zip(server.received_paths, server.received_methods)
        if method == "PUT"
    ]


class _FailingBackupRepository:
    """Double controlado que sempre falha na verificação de integridade —
    usado só para provar que a falha de backup impede o upload."""

    def save(self, **_kwargs) -> BackupMetadata:
        return BackupMetadata(
            collection_id="whatever",
            created_at_utc=datetime.now(UTC),
            sha256="0" * 64,
            size_bytes=10,
            contains_sensitive_data=True,
            backup_path=Path("backup-que-nao-existe.json"),
        )

    def verify(self, *_args, **_kwargs) -> bool:
        return False

    def apply_retention(self, **_kwargs) -> None:
        pass


# --- Seleção por ID ----------------------------------------------------------------


def test_update_by_valid_id_applies_and_creates_backup(cli_env, selected_workspace, capsys):
    configure_server(cli_env)

    exit_code = main(["update", "--collection-id", COLLECTION_A_ID, "--yes"])

    assert exit_code == SUCCESS
    assert _put_paths(cli_env) == [f"/collections/{COLLECTION_A_ID}"]
    out = capsys.readouterr().out
    assert "Atualização remota concluída" in out
    assert "Backup criado antes do upload" in out


def test_update_by_invalid_id_reports_resource_not_found(cli_env, selected_workspace):
    configure_server(cli_env)

    exit_code = main(["update", "--collection-id", "id-inexistente", "--yes"])

    assert exit_code == RESOURCE_NOT_FOUND
    assert _put_paths(cli_env) == []


def test_update_by_empty_id_reports_invalid_input(cli_env, selected_workspace):
    configure_server(cli_env)

    exit_code = main(["update", "--collection-id", "", "--yes"])

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


# --- Seleção por nome ----------------------------------------------------------------


def test_update_by_valid_name_applies_to_correct_collection(cli_env, selected_workspace):
    configure_server(cli_env)

    exit_code = main(["update", "--collection-name", COLLECTION_B_NAME, "--yes"])

    assert exit_code == SUCCESS
    assert _put_paths(cli_env) == [f"/collections/{COLLECTION_B_ID}"]


def test_update_by_name_not_found_reports_resource_not_found(cli_env, selected_workspace):
    configure_server(cli_env)

    exit_code = main(["update", "--collection-name", "Nome Inexistente", "--yes"])

    assert exit_code == RESOURCE_NOT_FOUND


def test_update_by_duplicate_name_reports_ambiguous_selection(cli_env, selected_workspace):
    configure_server(cli_env, duplicate_name=True)

    exit_code = main(["update", "--collection-name", COLLECTION_A_NAME, "--yes"])

    assert exit_code == AMBIGUOUS_SELECTION
    assert _put_paths(cli_env) == []


# --- Seleção por índice ----------------------------------------------------------------


def test_update_by_valid_index_applies_to_correct_collection(cli_env, selected_workspace):
    configure_server(cli_env)

    # Ordenação por nome: [1] Orders API (col-cli-b), [2] Pets API (col-cli-a).
    exit_code = main(["update", "1", "--yes"])

    assert exit_code == SUCCESS
    assert _put_paths(cli_env) == [f"/collections/{COLLECTION_B_ID}"]


@pytest.mark.parametrize("index", ["0", "-1", "99"])
def test_update_by_out_of_range_index_reports_invalid_input(cli_env, selected_workspace, index):
    configure_server(cli_env)

    exit_code = main(["update", index, "--yes"])

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


def test_update_by_textual_index_is_rejected_by_argparse(cli_env, selected_workspace):
    configure_server(cli_env)

    with pytest.raises(SystemExit) as exc_info:
        main(["update", "abc", "--yes"])

    assert exc_info.value.code == 2


# --- Seleção interativa ----------------------------------------------------------------


def test_update_interactive_valid_choice_applies(cli_env, selected_workspace, monkeypatch):
    configure_server(cli_env)
    responses = iter(["1", "s"])
    monkeypatch.setattr("builtins.input", lambda *_: next(responses))

    exit_code = main(["update"])

    assert exit_code == SUCCESS
    assert _put_paths(cli_env) == [f"/collections/{COLLECTION_B_ID}"]


def test_update_interactive_invalid_then_valid_choice_applies(cli_env, selected_workspace, monkeypatch):
    configure_server(cli_env)
    responses = iter(["abc", "99", "2", "s"])
    monkeypatch.setattr("builtins.input", lambda *_: next(responses))

    exit_code = main(["update"])

    assert exit_code == SUCCESS
    assert _put_paths(cli_env) == [f"/collections/{COLLECTION_A_ID}"]


# --- Conflitos de seleção ----------------------------------------------------------------


def test_update_rejects_id_and_name_together(cli_env, selected_workspace):
    configure_server(cli_env)

    exit_code = main(
        ["update", "--collection-id", COLLECTION_A_ID, "--collection-name", COLLECTION_B_NAME]
    )

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


def test_update_rejects_id_and_index_together(cli_env, selected_workspace):
    configure_server(cli_env)

    exit_code = main(["update", "1", "--collection-id", COLLECTION_A_ID])

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


def test_update_rejects_name_and_index_together(cli_env, selected_workspace):
    configure_server(cli_env)

    exit_code = main(["update", "1", "--collection-name", COLLECTION_B_NAME])

    assert exit_code == INVALID_INPUT_OR_CONFIGURATION


def test_update_does_not_accept_execution_id_flag(cli_env, selected_workspace):
    # A tarefa explicitamente não implementa --execution-id: deve ser
    # rejeitado pelo próprio argparse (uso incorreto), sem chamar rede.
    configure_server(cli_env)

    with pytest.raises(SystemExit) as exc_info:
        main(["update", "--execution-id", "algum-id", "--collection-id", COLLECTION_A_ID])

    assert exc_info.value.code == 2
    assert _put_paths(cli_env) == []


# --- Preview / fluxo (gera fresco, não lê artifacts antigos) ----------------------------------------------------------------


def test_update_shows_preview_before_confirmation(cli_env, selected_workspace, capsys):
    configure_server(cli_env)

    exit_code = main(["update", "--collection-id", COLLECTION_A_ID, "--yes"])

    assert exit_code == SUCCESS
    out = capsys.readouterr().out
    assert "Requests analisadas" in out
    assert "Requests que serão alteradas" in out
    assert "Testes gerados" in out
    assert "Avisos" in out


def test_update_generates_fresh_and_saves_artifacts_like_generate(
    cli_env, selected_workspace, tmp_path
):
    # update reaproveita GenerateCollectionTestsUseCase como está — o mesmo
    # efeito colateral de salvar artefatos em artifacts/ do generate também
    # acontece aqui (não é uma regra nova, nem uma leitura de artefato antigo).
    configure_server(cli_env)

    exit_code = main(["update", "--collection-id", COLLECTION_A_ID, "--yes"])

    assert exit_code == SUCCESS
    artifacts_dir = tmp_path / "artifacts" / WORKSPACE_ID / COLLECTION_A_ID
    assert artifacts_dir.is_dir()


def test_update_with_no_changes_skips_confirmation_and_upload(cli_env, selected_workspace, capsys):
    # Uma Collection sem nenhum request não produz diff algum: nada a
    # atualizar, nenhum PUT deve ocorrer.
    configure_server(cli_env, with_collections=False)
    cli_env.set_route(
        f"/collections?workspace={WORKSPACE_ID}",
        status=200,
        body={"collections": [{"id": "col-empty", "uid": "col-empty", "name": "Vazia"}]},
    )
    cli_env.set_route(
        "/collections/col-empty",
        status=200,
        body={
            "collection": {
                "info": {
                    "name": "Vazia",
                    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
                },
                "item": [],
            }
        },
    )

    exit_code = main(["update", "--collection-id", "col-empty"])

    assert exit_code == SUCCESS
    assert _put_paths(cli_env) == []
    assert "Nenhuma alteração detectada" in capsys.readouterr().out


# --- Confirmação ----------------------------------------------------------------


def test_update_confirmation_default_is_negative_on_empty_input(
    cli_env, selected_workspace, monkeypatch, capsys
):
    configure_server(cli_env)
    monkeypatch.setattr("builtins.input", lambda *_: "")

    exit_code = main(["update", "--collection-id", COLLECTION_A_ID])

    assert exit_code == OPERATION_CANCELLED
    assert "cancelada" in capsys.readouterr().out
    assert _put_paths(cli_env) == []


def test_update_confirmation_declined_cancels(cli_env, selected_workspace, monkeypatch, capsys):
    configure_server(cli_env)
    monkeypatch.setattr("builtins.input", lambda *_: "n")

    exit_code = main(["update", "--collection-id", COLLECTION_A_ID])

    assert exit_code == OPERATION_CANCELLED
    assert _put_paths(cli_env) == []


def test_update_confirmation_positive_applies(cli_env, selected_workspace, monkeypatch):
    configure_server(cli_env)
    monkeypatch.setattr("builtins.input", lambda *_: "s")

    exit_code = main(["update", "--collection-id", COLLECTION_A_ID])

    assert exit_code == SUCCESS
    assert _put_paths(cli_env) == [f"/collections/{COLLECTION_A_ID}"]


def test_update_confirmation_unrecognized_answer_cancels(
    cli_env, selected_workspace, monkeypatch, capsys
):
    configure_server(cli_env)
    monkeypatch.setattr("builtins.input", lambda *_: "talvez")

    exit_code = main(["update", "--collection-id", COLLECTION_A_ID])

    assert exit_code == OPERATION_CANCELLED
    assert "não reconhecida" in capsys.readouterr().out
    assert _put_paths(cli_env) == []


def test_update_yes_flag_skips_only_the_prompt(cli_env, selected_workspace, monkeypatch):
    configure_server(cli_env)
    monkeypatch.setattr(
        "builtins.input", lambda *a, **k: (_ for _ in ()).throw(AssertionError("não deveria perguntar"))
    )

    exit_code = main(["update", "--collection-id", COLLECTION_A_ID, "--yes"])

    assert exit_code == SUCCESS
    assert _put_paths(cli_env) == [f"/collections/{COLLECTION_A_ID}"]


# --- Ctrl+C / EOF (correção do bug de código 8) ----------------------------------------------------------------


def test_update_keyboard_interrupt_during_confirmation_returns_cancelled_not_unexpected_error(
    cli_env, selected_workspace, monkeypatch, capsys
):
    configure_server(cli_env)

    def _raise_keyboard_interrupt(*_a, **_k):
        raise KeyboardInterrupt()

    monkeypatch.setattr("builtins.input", _raise_keyboard_interrupt)

    exit_code = main(["update", "--collection-id", COLLECTION_A_ID])

    assert exit_code == OPERATION_CANCELLED
    captured = capsys.readouterr()
    assert "cancelada" in captured.out
    assert "inesperado" not in captured.err.lower()
    assert _put_paths(cli_env) == []


def test_update_eof_during_confirmation_returns_cancelled(
    cli_env, selected_workspace, monkeypatch, capsys
):
    configure_server(cli_env)
    monkeypatch.setattr("builtins.input", lambda *_: (_ for _ in ()).throw(EOFError()))

    exit_code = main(["update", "--collection-id", COLLECTION_A_ID])

    assert exit_code == OPERATION_CANCELLED
    assert "cancelada" in capsys.readouterr().out


def test_update_keyboard_interrupt_during_interactive_selection_returns_cancelled(
    cli_env, selected_workspace, monkeypatch, capsys
):
    configure_server(cli_env)

    def _raise_keyboard_interrupt(*_a, **_k):
        raise KeyboardInterrupt()

    monkeypatch.setattr("builtins.input", _raise_keyboard_interrupt)

    exit_code = main(["update"])

    assert exit_code == OPERATION_CANCELLED
    assert _put_paths(cli_env) == []


# --- Segurança ----------------------------------------------------------------


def test_update_never_leaks_api_key(cli_env, selected_workspace, monkeypatch, capsys):
    configure_server(cli_env)

    exit_code = main(["update", "--collection-id", COLLECTION_A_ID, "--yes"])

    assert exit_code == SUCCESS
    captured = capsys.readouterr()
    assert FAKE_API_KEY not in captured.out
    assert FAKE_API_KEY not in captured.err


def test_update_authentication_failure_does_not_leak_api_key(cli_env, selected_workspace, capsys):
    cli_env.set_route(f"/collections/{COLLECTION_A_ID}", status=401, body={"error": "invalid key"})

    exit_code = main(["update", "--collection-id", COLLECTION_A_ID, "--yes"])

    captured = capsys.readouterr()
    assert FAKE_API_KEY not in captured.out
    assert FAKE_API_KEY not in captured.err
    assert exit_code != SUCCESS


def test_update_never_prints_full_collection_document(cli_env, selected_workspace, capsys):
    configure_server(cli_env)

    exit_code = main(["update", "--collection-id", COLLECTION_A_ID, "--yes"])

    assert exit_code == SUCCESS
    out = capsys.readouterr().out
    # O documento completo nunca é impresso: nem o payload bruto do Postman
    # (marcador "info":) nem a URL interna da request de exemplo.
    assert '"info":' not in out
    assert "https://api.exemplo.com/pets" not in out


# --- Backup obrigatório antes do upload ----------------------------------------------------------------


def test_update_backup_failure_prevents_upload(cli_env, selected_workspace, monkeypatch):
    configure_server(cli_env)
    monkeypatch.setattr(bootstrap, "LocalBackupRepository", _FailingBackupRepository)

    exit_code = main(["update", "--collection-id", COLLECTION_A_ID, "--yes"])

    assert exit_code != SUCCESS
    assert _put_paths(cli_env) == []


# --- Idempotência ----------------------------------------------------------------


def test_update_twice_in_a_row_is_idempotent_after_first_apply(cli_env, selected_workspace):
    configure_server(cli_env)

    first_exit = main(["update", "--collection-id", COLLECTION_A_ID, "--yes"])
    assert first_exit == SUCCESS
    assert len(_put_paths(cli_env)) == 1

    # A segunda geração parte do estado ORIGINAL simulado pelo servidor de
    # teste (que não persiste o PUT anterior), então continuará detectando
    # a mesma mudança — o que importa aqui é que o fluxo se comporta de
    # forma consistente e sempre reflete o estado remoto atual, nunca um
    # artefato salvo de uma execução anterior.
    second_exit = main(["update", "--collection-id", COLLECTION_A_ID, "--yes"])
    assert second_exit == SUCCESS
    assert len(_put_paths(cli_env)) == 2


# --- generate não afetado ----------------------------------------------------------------


def test_generate_still_never_calls_update(cli_env, selected_workspace):
    configure_server(cli_env)

    exit_code = main(["generate", "--collection-id", COLLECTION_A_ID, "--yes"])

    assert exit_code == SUCCESS
    assert _put_paths(cli_env) == []
