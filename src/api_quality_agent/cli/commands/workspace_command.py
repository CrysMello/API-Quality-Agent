import argparse

from api_quality_agent.cli import bootstrap
from api_quality_agent.cli.bootstrap import CliContext
from api_quality_agent.cli.exit_codes import OPERATION_CANCELLED, SUCCESS
from api_quality_agent.domain.exceptions import AmbiguousResourceError, InputError, ResourceNotFoundError
from api_quality_agent.domain.models import WorkspaceRef

_CONFIRM_VALUES = frozenset({"", "s", "sim", "y", "yes"})
_CANCEL_VALUES = frozenset({"n", "nao", "não", "no"})


class _OperationCancelled(Exception):
    pass


def register(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    workspace_parser = subparsers.add_parser(
        "workspace", help="Lista e seleciona o Workspace ativo."
    )
    workspace_subparsers = workspace_parser.add_subparsers(
        dest="workspace_command", required=True
    )

    list_parser = workspace_subparsers.add_parser(
        "list", help="Lista os Workspaces disponíveis."
    )
    list_parser.set_defaults(handler=_handle_list)

    select_parser = workspace_subparsers.add_parser(
        "select", help="Seleciona o Workspace ativo."
    )
    select_parser.add_argument(
        "index",
        nargs="?",
        type=int,
        default=None,
        metavar="INDEX",
        help="Índice do Workspace na listagem atual.",
    )
    select_parser.add_argument(
        "-i", "--workspace-id", dest="workspace_id", default=None, help="ID do Workspace."
    )
    select_parser.add_argument(
        "-n",
        "--workspace-name",
        dest="workspace_name",
        default=None,
        help="Nome do Workspace.",
    )
    select_parser.add_argument(
        "-y",
        "--yes",
        dest="yes",
        action="store_true",
        help="Não solicitar confirmação final.",
    )
    select_parser.set_defaults(handler=_handle_select)


def _handle_list(_args: argparse.Namespace) -> int:
    context = bootstrap.build_context()
    workspaces = context.list_workspaces_use_case.execute()

    if not workspaces:
        print("Nenhum Workspace foi encontrado para a API Key configurada.")
        return SUCCESS

    print("Workspaces disponíveis:\n")
    for index, workspace in enumerate(bootstrap.sort_workspaces(workspaces), start=1):
        print(f"[{index}] {workspace.name}")
        print(f"    ID: {workspace.id}\n")

    return SUCCESS


def _handle_select(args: argparse.Namespace) -> int:
    _validate_selection_arguments(args)

    context = bootstrap.build_context()

    try:
        selected = _select_workspace(context, args)
    except _OperationCancelled:
        print("Operação cancelada pelo usuário.")
        return OPERATION_CANCELLED

    print(f"Workspace selecionado: {selected.name}")
    print(f"Workspace ID: {selected.id}\n")

    if not args.yes and not _confirm():
        print("Operação cancelada pelo usuário.")
        return OPERATION_CANCELLED

    # A seleção só é persistida após a confirmação — seleção temporária de
    # exibição (linhas acima) não deve ser confundida com a seleção ativa
    # salva em disco, que só passa a valer a partir daqui.
    context.select_workspace_use_case.execute(workspace_id=selected.id)

    print(f"Workspace ativo atualizado para: {selected.name}")
    return SUCCESS


def _validate_selection_arguments(args: argparse.Namespace) -> None:
    provided = [
        value is not None
        for value in (args.index, args.workspace_id, args.workspace_name)
    ]
    if sum(provided) > 1:
        raise InputError(
            "informe somente uma forma de seleção do Workspace. Use ID, nome ou índice."
        )


def _select_workspace(context: CliContext, args: argparse.Namespace) -> WorkspaceRef:
    # Resolução apenas: nenhum destes ramos persiste a seleção. A
    # persistência acontece só depois da confirmação, em _handle_select,
    # via select_workspace_use_case.execute(workspace_id=selected.id) — a
    # mesma "seleção temporária" usada por generate_command para Collections.
    if args.workspace_id is not None:
        return _resolve_by_id(context, args.workspace_id)

    if args.workspace_name is not None:
        return _resolve_by_name(context, args.workspace_name)

    if args.index is not None:
        return _select_by_index(context, args.index)

    return _select_interactively(context)


def _resolve_by_id(context: CliContext, workspace_id: str) -> WorkspaceRef:
    if not workspace_id:
        raise InputError("Informe o ID ou o nome do Workspace a selecionar.")
    workspaces = context.list_workspaces_use_case.execute()
    match = next((workspace for workspace in workspaces if workspace.id == workspace_id), None)
    if match is None:
        raise ResourceNotFoundError(f"Workspace com ID '{workspace_id}' não encontrado.")
    return match


def _resolve_by_name(context: CliContext, workspace_name: str) -> WorkspaceRef:
    if not workspace_name:
        raise InputError("Informe o ID ou o nome do Workspace a selecionar.")
    workspaces = context.list_workspaces_use_case.execute()
    matches = [workspace for workspace in workspaces if workspace.name == workspace_name]
    if not matches:
        raise ResourceNotFoundError(f"Workspace com nome '{workspace_name}' não encontrado.")
    if len(matches) > 1:
        raise AmbiguousResourceError(
            f"Múltiplos Workspaces encontrados com o nome '{workspace_name}'. "
            "Utilize o ID para selecionar um deles."
        )
    return matches[0]


def _select_by_index(context: CliContext, index: int) -> WorkspaceRef:
    workspaces = bootstrap.sort_workspaces(context.list_workspaces_use_case.execute())
    if not workspaces:
        raise InputError("Nenhum Workspace foi encontrado para a API Key configurada.")
    if index < 1 or index > len(workspaces):
        raise InputError(
            f"opção {index} inválida. Existem {len(workspaces)} Workspaces disponíveis."
        )
    return workspaces[index - 1]


def _select_interactively(context: CliContext) -> WorkspaceRef:
    workspaces = bootstrap.sort_workspaces(context.list_workspaces_use_case.execute())
    if not workspaces:
        raise InputError("Nenhum Workspace foi encontrado para a API Key configurada.")

    print("Workspaces disponíveis:\n")
    for index, workspace in enumerate(workspaces, start=1):
        print(f"[{index}] {workspace.name}")
        print(f"    ID: {workspace.id}\n")

    while True:
        raw = _read_line("Selecione um Workspace: ")
        text = raw.strip()
        if not text:
            print("Entrada inválida. Digite o número correspondente ao Workspace.")
            continue
        try:
            choice = int(text)
        except ValueError:
            print("Entrada inválida. Digite o número correspondente ao Workspace.")
            continue
        if choice < 1 or choice > len(workspaces):
            print(f"Opção inválida. Escolha um número entre 1 e {len(workspaces)}.")
            continue
        return workspaces[choice - 1]


def _confirm() -> bool:
    raw = _read_line("Deseja continuar? [S/n]: ")
    answer = raw.strip().lower()
    if answer in _CANCEL_VALUES:
        return False
    if answer in _CONFIRM_VALUES:
        return True
    print("Entrada não reconhecida.")
    return False


def _read_line(prompt: str) -> str:
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        raise _OperationCancelled() from None
