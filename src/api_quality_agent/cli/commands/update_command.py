import argparse

from api_quality_agent.application.orchestration import CollectionGenerationResult
from api_quality_agent.application.use_cases import CollectionUpdateResult
from api_quality_agent.cli import bootstrap, collection_selection
from api_quality_agent.cli.exit_codes import OPERATION_CANCELLED, SUCCESS
from api_quality_agent.cli.interactive import OperationCancelled, confirm
from api_quality_agent.domain.models import DiffCategory, WorkspaceRef
from api_quality_agent.domain.services import ApprovalPolicy

_UPDATE_CONFIRMATION_PROMPT = (
    "\nA Collection remota será atualizada.\n"
    "Um backup será criado antes do upload.\n\n"
    "Deseja continuar? [s/N]: "
)


def register(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = subparsers.add_parser(
        "update",
        help=(
            "Gera novamente os testes a partir do estado atual da Collection "
            "e aplica a atualização remota no Postman."
        ),
    )
    collection_selection.add_selection_arguments(parser)
    parser.add_argument(
        "-y",
        "--yes",
        dest="yes",
        action="store_true",
        help="Não solicitar confirmação final (as demais validações continuam ocorrendo).",
    )
    parser.set_defaults(handler=_handle_update)


def _handle_update(args: argparse.Namespace) -> int:
    collection_selection.validate_selection_arguments(args)

    context = bootstrap.build_context()
    workspace_ref = bootstrap.resolve_active_workspace(context)

    try:
        selected = collection_selection.select_collection(context, workspace_ref.id, args)
    except OperationCancelled:
        print("Operação cancelada pelo usuário.")
        return OPERATION_CANCELLED

    print(f"Workspace: {workspace_ref.name}")
    print(f"Collection: {selected.name}")
    print(f"Collection ID: {selected.id}\n")
    print("Baixando o estado atual da Collection e gerando os testes novamente...")

    # O CollectionGenerationResult usado no preview é exatamente o mesmo
    # entregue ao UpdateCollectionUseCase logo abaixo — nenhuma nova geração
    # ocorre depois da confirmação, e nada é lido de execuções anteriores do
    # generate (nenhum artefato em artifacts/ é consultado aqui).
    result = context.generate_use_case.execute(collection_id=selected.id)

    _print_preview(workspace_ref, result)

    if not result.diff.has_changes:
        print("\nNenhuma alteração detectada; nada a atualizar.")
        return SUCCESS

    try:
        if not args.yes and not confirm(_UPDATE_CONFIRMATION_PROMPT, default=False):
            print("Operação cancelada pelo usuário.")
            return OPERATION_CANCELLED
    except OperationCancelled:
        print("Operação cancelada pelo usuário.")
        return OPERATION_CANCELLED

    # explicit_yes=True só é alcançado depois da confirmação (interativa ou
    # --yes) acima; allow_removals permanece False sempre — toda remoção
    # continua sendo risco alto e bloqueia a atualização, sem uma flag para
    # contornar isso nesta tarefa.
    approval_policy = ApprovalPolicy(dry_run=False, explicit_yes=True, allow_removals=False)
    update_result = context.update_use_case.execute(result, approval_policy)

    _print_update_result(update_result)
    return SUCCESS


def _print_preview(workspace_ref: WorkspaceRef, result: CollectionGenerationResult) -> None:
    changed_requests = _count_changed_requests(result)
    total_requests = len(result.endpoint_outcomes)
    tests_generated = sum(
        1 for outcome in result.endpoint_outcomes if outcome.generated_script is not None
    )
    warnings_count = len(result.analysis_warnings) + sum(
        len(outcome.schema_warnings) + len(outcome.strategy_warnings)
        for outcome in result.endpoint_outcomes
    )

    print(f"\nWorkspace: {workspace_ref.name}")
    print(f"Collection: {result.execution_context.collection_name}")
    print(f"Collection ID: {result.execution_context.collection_id}\n")
    print(f"Requests analisadas: {total_requests}")
    print(f"Requests que serão alteradas: {changed_requests}")
    print(f"Requests sem alterações: {total_requests - changed_requests}")
    print(f"Testes gerados: {tests_generated}")
    print(f"Avisos: {warnings_count}")


def _count_changed_requests(result: CollectionGenerationResult) -> int:
    # Reaproveita o diff já calculado pelo GenerateCollectionTestsUseCase —
    # apenas resume, para exibição, quantas requests distintas tiveram um
    # bloco de script adicionado ou modificado (nenhuma regra de diff nova).
    labels = {
        entry.target.split(" > ", 1)[0]
        for entry in result.diff.entries
        if entry.category == DiffCategory.SCRIPT
    }
    return len(labels)


def _print_update_result(update_result: CollectionUpdateResult) -> None:
    print("\nAtualização remota concluída com sucesso.\n")
    print(f"Collection ID: {update_result.collection_id}")
    if update_result.backup_created:
        print("Backup criado antes do upload:")
        print(f"  Caminho: {update_result.backup_path}")
        print(f"  SHA-256: {update_result.backup_sha256}")
    print(f"Status HTTP: {update_result.status_code}")
