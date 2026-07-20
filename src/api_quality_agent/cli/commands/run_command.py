import argparse
import sys
from datetime import datetime

from api_quality_agent.cli import bootstrap, collection_selection
from api_quality_agent.cli.exit_codes import (
    FUNCTIONAL_FAILURE,
    INTEGRATION_FAILURE,
    OPERATION_CANCELLED,
    SUCCESS,
)
from api_quality_agent.cli.interactive import OperationCancelled
from api_quality_agent.domain.models import ExecutionResult, InfrastructureFailureType

_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def register(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = subparsers.add_parser(
        "run", help="Executa a Collection selecionada via Newman."
    )
    collection_selection.add_selection_arguments(parser)
    parser.add_argument(
        "-f",
        "--file",
        dest="file",
        default=None,
        metavar="COLLECTION_JSON",
        help=(
            "Executa uma Collection exportada localmente (arquivo .json), "
            "sem conectar à API do Postman."
        ),
    )
    parser.add_argument(
        "--newman-executable",
        dest="newman_executable",
        default=None,
        metavar="CAMINHO",
        help=(
            "Caminho do executável do Newman. Precedência: esta flag > "
            "variável de ambiente NEWMAN_EXECUTABLE > \"newman\"."
        ),
    )
    parser.add_argument(
        "-e",
        "--environment",
        dest="environment",
        default=None,
        metavar="ENVIRONMENT_JSON",
        help="Arquivo de Environment do Postman a usar na execução.",
    )
    parser.set_defaults(handler=_handle_run)


def _handle_run(args: argparse.Namespace) -> int:
    collection_selection.validate_selection_arguments(args, extra_fields=("file",))

    if args.file is not None:
        return _handle_run_from_file(args)

    context = bootstrap.build_context(newman_executable=args.newman_executable)
    workspace_ref = bootstrap.resolve_active_workspace(context)

    try:
        selected = collection_selection.select_collection(context, workspace_ref.id, args)

        print(f"Executando '{selected.name}' via Newman...")

        started_at = datetime.now()
        try:
            result = context.run_use_case.execute(
                collection_id=selected.id, environment_path=args.environment
            )
        except KeyboardInterrupt:
            raise OperationCancelled() from None
        finished_at = datetime.now()
    except OperationCancelled:
        print("Operação cancelada pelo usuário.")
        return OPERATION_CANCELLED

    if result.infrastructure_failure is not None:
        _print_infrastructure_failure(result)
        return INTEGRATION_FAILURE

    _print_summary(workspace_ref.name, selected.name, result, started_at, finished_at)
    _persist_result(
        context.persist_execution_result_use_case,
        result,
        collection_id=selected.id,
        collection_name=selected.name,
        workspace_id=workspace_ref.id,
        workspace_name=workspace_ref.name,
        started_at=started_at,
        finished_at=finished_at,
    )

    return _final_exit_code(result)


def _handle_run_from_file(args: argparse.Namespace) -> int:
    context = bootstrap.build_offline_run_context(newman_executable=args.newman_executable)

    resolved_input = context.input_resolver.resolve_from_file(args.file)
    document = context.collection_parser.parse(resolved_input)

    print(f"Executando '{document.name}' via Newman (arquivo local)...")

    started_at = datetime.now()
    try:
        result = context.run_use_case.execute(
            local_collection_path=args.file, environment_path=args.environment
        )
    except KeyboardInterrupt:
        print("Operação cancelada pelo usuário.")
        return OPERATION_CANCELLED
    finished_at = datetime.now()

    if result.infrastructure_failure is not None:
        _print_infrastructure_failure(result)
        return INTEGRATION_FAILURE

    _print_summary(None, document.name, result, started_at, finished_at)
    _persist_result(
        context.persist_execution_result_use_case,
        result,
        collection_id=None,
        collection_name=document.name,
        workspace_id=None,
        workspace_name=None,
        started_at=started_at,
        finished_at=finished_at,
    )

    return _final_exit_code(result)


def _final_exit_code(result: ExecutionResult) -> int:
    if result.success:
        print("\nExecution finished successfully.")
        return SUCCESS

    print("\nExecution finished with test failures.")
    return FUNCTIONAL_FAILURE


def _persist_result(
    persist_execution_result_use_case: bootstrap.PersistExecutionResultUseCase,
    result: ExecutionResult,
    *,
    collection_id: str | None,
    collection_name: str | None,
    workspace_id: str | None,
    workspace_name: str | None,
    started_at: datetime,
    finished_at: datetime,
) -> None:
    # A execução dos testes e a persistência do resultado são
    # responsabilidades distintas: uma falha ao gravar o result.json nunca
    # transforma uma execução bem-sucedida (ou com falhas de teste) em erro
    # de infraestrutura — só é comunicada como um aviso à parte.
    try:
        location = persist_execution_result_use_case.execute(
            result,
            collection_id=collection_id,
            collection_name=collection_name,
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            started_at=started_at,
            finished_at=finished_at,
        )
    except Exception as exc:
        print(f"\nAviso: não foi possível salvar o resultado da execução: {exc}", file=sys.stderr)
        return

    print(f"\nResult saved to:\n  {location.path}")


def _print_summary(
    workspace_name: str | None,
    collection_name: str,
    result: ExecutionResult,
    started_at: datetime,
    finished_at: datetime,
) -> None:
    passed = result.total_assertions - result.failed_assertions
    print("\nExecution Summary")
    print("-" * 40)
    print(f"Workspace: {workspace_name or 'N/A (execução local)'}")
    print(f"Collection: {collection_name}")
    print(f"Started: {started_at.strftime(_TIMESTAMP_FORMAT)}")
    print(f"Finished: {finished_at.strftime(_TIMESTAMP_FORMAT)}")
    print(f"Duration: {result.duration_seconds:.1f} s")
    print(f"Requests: {result.total_requests}")
    print(f"Assertions: {result.total_assertions}")
    print(f"Passed: {passed}")
    print(f"Failed: {result.failed_assertions}")


def _print_infrastructure_failure(result: ExecutionResult) -> None:
    failure = result.infrastructure_failure
    assert failure is not None  # já verificado pelo chamador
    print("\nNewman execution failed due to an infrastructure error.")
    print(failure.message)
    if failure.failure_type == InfrastructureFailureType.EXECUTABLE_NOT_FOUND:
        print(
            "\nConfigure o executável usando:\n"
            "  --newman-executable <caminho>\n"
            "ou:\n"
            "  NEWMAN_EXECUTABLE=<caminho>"
        )
