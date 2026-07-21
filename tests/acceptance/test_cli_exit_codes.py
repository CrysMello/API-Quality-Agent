"""Verifica que as exceções realmente lançadas pelos fluxos do MVP mapeiam
para os códigos de saída corretos da CLI (api_quality_agent.cli.exit_codes),
o mesmo mapeamento usado por cli.main._dispatch para qualquer comando.
"""

import pytest
from conftest import COLLECTION_A_ID, COLLECTION_A_NAME, WORKSPACE_ID, build_app, configure_server

from api_quality_agent.cli.exit_codes import (
    AMBIGUOUS_SELECTION,
    AUTHENTICATION_FAILURE,
    INVALID_INPUT_OR_CONFIGURATION,
    RESOURCE_NOT_FOUND,
    SUCCESS,
    UPDATE_NOT_APPROVED,
    resolve_exit_code,
)
from api_quality_agent.domain.exceptions import (
    AmbiguousResourceError,
    AuthenticationError,
    CorruptedInputFileError,
    EmptyInputError,
    InputError,
    InputFileNotFoundError,
    ResourceNotFoundError,
    UpdateNotApprovedError,
)
from api_quality_agent.domain.services import ApprovalPolicy
from api_quality_agent.parsers import ExcelContractParser


def test_successful_workspace_selection_maps_to_success_exit_code(postman_test_server, tmp_path):
    configure_server(postman_test_server)
    app = build_app(postman_test_server, tmp_path)

    app.select_workspace.execute(workspace_id=WORKSPACE_ID)

    assert SUCCESS == 0  # nenhuma exceção foi lançada: o comando terminaria com exit 0


def test_authentication_failure_maps_to_authentication_exit_code(postman_test_server, tmp_path):
    postman_test_server.set_route("/workspaces", status=401, body={"error": "invalid key"})
    app = build_app(postman_test_server, tmp_path)

    with pytest.raises(AuthenticationError) as exc_info:
        app.list_workspaces.execute()

    assert resolve_exit_code(exc_info.value) == AUTHENTICATION_FAILURE


def test_ambiguous_collection_name_maps_to_ambiguous_selection_exit_code(
    postman_test_server, tmp_path
):
    configure_server(postman_test_server, duplicate_name=True)
    app = build_app(postman_test_server, tmp_path)
    app.select_workspace.execute(workspace_id=WORKSPACE_ID)

    with pytest.raises(AmbiguousResourceError) as exc_info:
        app.select_collection.execute(collection_name=COLLECTION_A_NAME)

    assert resolve_exit_code(exc_info.value) == AMBIGUOUS_SELECTION


def test_collection_not_found_maps_to_resource_not_found_exit_code(postman_test_server, tmp_path):
    configure_server(postman_test_server)
    app = build_app(postman_test_server, tmp_path)
    app.select_workspace.execute(workspace_id=WORKSPACE_ID)

    with pytest.raises(ResourceNotFoundError) as exc_info:
        app.select_collection.execute(collection_id="collection-inexistente")

    assert resolve_exit_code(exc_info.value) == RESOURCE_NOT_FOUND


def test_update_without_approval_maps_to_update_not_approved_exit_code(
    postman_test_server, tmp_path
):
    configure_server(postman_test_server)
    app = build_app(postman_test_server, tmp_path)
    app.select_workspace.execute(workspace_id=WORKSPACE_ID)
    app.select_collection.execute(collection_id=COLLECTION_A_ID)
    result = app.generate_use_case.execute()

    with pytest.raises(UpdateNotApprovedError) as exc_info:
        app.update_use_case.execute(result, ApprovalPolicy())

    assert resolve_exit_code(exc_info.value) == UPDATE_NOT_APPROVED


def test_missing_workspace_selection_maps_to_invalid_input_exit_code(postman_test_server, tmp_path):
    configure_server(postman_test_server)
    app = build_app(postman_test_server, tmp_path)

    with pytest.raises(InputError) as exc_info:
        app.list_collections.execute()

    assert resolve_exit_code(exc_info.value) == INVALID_INPUT_OR_CONFIGURATION


# Correção dos exit codes (R2): arquivo de contrato Excel inexistente/vazio/
# corrompido lançado por ExcelContractParser.parse() precisa mapear pro
# mesmo código 2 usado por qualquer outra entrada inválida — antes desta
# correção, essas exceções cruas do openpyxl escapavam sem tradução e
# caíam no catch-all de cli.main, resultando no código 8 (erro inesperado).


def test_nonexistent_contract_file_maps_to_invalid_input_exit_code(tmp_path):
    missing_path = tmp_path / "nao_existe.xlsx"

    with pytest.raises(InputFileNotFoundError) as exc_info:
        ExcelContractParser().parse(missing_path)

    assert resolve_exit_code(exc_info.value) == INVALID_INPUT_OR_CONFIGURATION


def test_empty_contract_file_maps_to_invalid_input_exit_code(tmp_path):
    empty_path = tmp_path / "vazio.xlsx"
    empty_path.write_bytes(b"")

    with pytest.raises(EmptyInputError) as exc_info:
        ExcelContractParser().parse(empty_path)

    assert resolve_exit_code(exc_info.value) == INVALID_INPUT_OR_CONFIGURATION


def test_corrupted_contract_file_maps_to_invalid_input_exit_code(tmp_path):
    corrupted_path = tmp_path / "corrompido.xlsx"
    corrupted_path.write_bytes(b"isto nao e um arquivo zip valido")

    with pytest.raises(CorruptedInputFileError) as exc_info:
        ExcelContractParser().parse(corrupted_path)

    assert resolve_exit_code(exc_info.value) == INVALID_INPUT_OR_CONFIGURATION
