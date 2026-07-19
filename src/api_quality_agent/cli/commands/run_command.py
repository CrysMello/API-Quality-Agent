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
from api_quality_agent.domain.models import ExecutionResult, InfrastructureFailureType, WorkspaceRef

_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def register(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = subparsers.add_parser(
        "run", help="Executa a Collection selecionada via Newman."
    )
    collection_selection.add_selection_arguments(parser)
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
    parser.set_defaults(handler=_handle_run)


def _handle_run(args: argparse.Namespace) -> int:
    collection_selection.validate_selection_arguments(args)

    context = bootstrap.build_context(newman_executable=args.newman_executable)
    workspace_ref = bootstrap.resolve_active_workspace(context)

    try:
        selected = collection_selection.select_collection(context, workspace_ref.id, args)

        print(f"Executando '{selected.name}' via Newman...")

        started_at = datetime.now()
        try:
            result = context.run_use_case.execute(collection_id=selected.id, environment_path=None)
        except KeyboardInterrupt:
            raise OperationCancelled() from None
        finished_at = datetime.now()
    except OperationCancelled:
        print("Operação cancelada pelo usuário.")
        return OPERATION_CANCELLED

    if result.infrastructure_failure is not None:
        _print_infrastructure_failure(result)
        return INTEGRATION_FAILURE

    _print_summary(workspace_ref, selected.name, result, started_at, finished_at)
    _persist_result(
        context,
        result,
        collection_id=selected.id,
        collection_name=selected.name,
        started_at=started_at,
        finished_at=finished_at,
    )

    if result.success:
        print("\nExecution finished successfully.")
        return SUCCESS

    print("\nExecution finished with test failures.")
    return FUNCTIONAL_FAILURE


def _persist_result(
    context: bootstrap.CliContext,
    result: ExecutionResult,
    *,
    collection_id: str,
    collection_name: str,
    started_at: datetime,
    finished_at: datetime,
) -> None:
    # A execução dos testes e a persistência do resultado são
    # responsabilidades distintas: uma falha ao gravar o result.json nunca
    # transforma uma execução bem-sucedida (ou com falhas de teste) em erro
    # de infraestrutura — só é comunicada como um aviso à parte.
    try:
        location = context.persist_execution_result_use_case.execute(
            result,
            collection_id=collection_id,
            collection_name=collection_name,
            started_at=started_at,
            finished_at=finished_at,
        )
    except Exception as exc:
        print(f"\nAviso: não foi possível salvar o resultado da execução: {exc}", file=sys.stderr)
        return

    print(f"\nResult saved to:\n  {location.path}")


def _print_summary(
    workspace_ref: WorkspaceRef,
    collection_name: str,
    result: ExecutionResult,
    started_at: datetime,
    finished_at: datetime,
) -> None:
    passed = result.total_assertions - result.failed_assertions
    print("\nExecution Summary")
    print("-" * 40)
    print(f"Workspace: {workspace_ref.name}")
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
