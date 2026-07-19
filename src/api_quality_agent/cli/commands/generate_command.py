import argparse

from api_quality_agent.cli import bootstrap
from api_quality_agent.cli.bootstrap import CliContext
from api_quality_agent.cli.exit_codes import OPERATION_CANCELLED, SUCCESS
from api_quality_agent.domain.exceptions import AmbiguousResourceError, InputError, ResourceNotFoundError
from api_quality_agent.domain.models import CollectionRef

_CONFIRM_VALUES = frozenset({"", "s", "sim", "y", "yes"})
_CANCEL_VALUES = frozenset({"n", "nao", "não", "no"})


class _OperationCancelled(Exception):
    pass


def register(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = subparsers.add_parser(
        "generate", help="Gera e aplica testes na Collection selecionada."
    )
    parser.add_argument(
        "index",
        nargs="?",
        type=int,
        default=None,
        metavar="INDEX",
        help="Índice da Collection na listagem atual.",
    )
    parser.add_argument(
        "-c", "--collection-id", dest="collection_id", default=None, help="ID da Collection."
    )
    parser.add_argument(
        "-n",
        "--collection-name",
        dest="collection_name",
        default=None,
        help="Nome da Collection.",
    )
    parser.add_argument(
        "-y",
        "--yes",
        dest="yes",
        action="store_true",
        help="Não solicitar confirmação final.",
    )
    parser.set_defaults(handler=_handle_generate)


def _handle_generate(args: argparse.Namespace) -> int:
    _validate_selection_arguments(args)

    context = bootstrap.build_context()
    workspace_ref = bootstrap.resolve_active_workspace(context)

    try:
        selected = _select_collection(context, workspace_ref.id, args)
    except _OperationCancelled:
        print("Operação cancelada pelo usuário.")
        return OPERATION_CANCELLED

    print(f"Workspace: {workspace_ref.name}")
    print(f"Collection selecionada: {selected.name}")
    print(f"Collection ID: {selected.id}\n")

    if not args.yes and not _confirm():
        print("Operação cancelada pelo usuário.")
        return OPERATION_CANCELLED

    print(f"\nCollection selecionada:\n{selected.name}\n")
    print("Gerando testes...")

    # collection_id é sempre passado explicitamente: a Collection já foi
    # resolvida acima (por ID, nome, índice ou interativamente) — isso é
    # sempre uma seleção temporária (ResolveCollectionUseCase nunca
    # persiste), nunca altera a seleção ativa salva em disco.
    result = context.generate_use_case.execute(collection_id=selected.id)

    print("Processo concluído com sucesso.\n")
    print(f"Endpoints processados: {len(result.endpoint_outcomes)}")
    failed_outcomes = [outcome for outcome in result.endpoint_outcomes if outcome.error is not None]
    if failed_outcomes:
        print(f"  Com falha: {len(failed_outcomes)}")
    print(f"Diff possui mudanças: {result.diff.has_changes}")
    print(f"Artefatos salvos: {len(result.artifact_locations)}")
    for location in result.artifact_locations:
        print(f"  - {location.path}")

    return SUCCESS


def _validate_selection_arguments(args: argparse.Namespace) -> None:
    provided = [
        value is not None
        for value in (args.index, args.collection_id, args.collection_name)
    ]
    if sum(provided) > 1:
        raise InputError(
            "informe somente uma forma de seleção da Collection. Use ID, nome ou índice."
        )


def _select_collection(
    context: CliContext, workspace_id: str, args: argparse.Namespace
) -> CollectionRef:
    if args.collection_id is not None:
        return context.selection_service.resolve(
            workspace_id=workspace_id, collection_id=args.collection_id
        )

    if args.collection_name is not None:
        return _select_by_name(context, workspace_id, args.collection_name)

    if args.index is not None:
        return _select_by_index(context, workspace_id, args.index)

    return _select_interactively(context, workspace_id)


def _select_by_name(context: CliContext, workspace_id: str, name: str) -> CollectionRef:
    try:
        return context.selection_service.resolve(workspace_id=workspace_id, collection_name=name)
    except AmbiguousResourceError:
        collections = context.collection_repository.list(workspace_id)
        matches = sorted(
            (collection for collection in collections if collection.name == name),
            key=lambda collection: collection.id,
        )
        raise AmbiguousResourceError(_format_ambiguous_matches(matches)) from None


def _format_ambiguous_matches(matches: list[CollectionRef]) -> str:
    lines = ["Foram encontradas várias Collections com o nome informado:\n"]
    for index, collection in enumerate(matches, start=1):
        lines.append(f"[{index}] {collection.name}")
        lines.append(f"    ID: {collection.id}\n")
    lines.append("Informe o ID da Collection desejada usando --collection-id.")
    return "\n".join(lines)


def _select_by_index(context: CliContext, workspace_id: str, index: int) -> CollectionRef:
    collections = bootstrap.sort_collections(context.collection_repository.list(workspace_id))
    if not collections:
        raise ResourceNotFoundError(
            "Nenhuma Collection foi encontrada no workspace configurado."
        )
    if index < 1 or index > len(collections):
        raise InputError(
            f"opção {index} inválida. Existem {len(collections)} Collections disponíveis."
        )
    return collections[index - 1]


def _select_interactively(context: CliContext, workspace_id: str) -> CollectionRef:
    collections = bootstrap.sort_collections(context.collection_repository.list(workspace_id))
    if not collections:
        raise ResourceNotFoundError(
            "Nenhuma Collection foi encontrada no workspace configurado."
        )

    print("Collections disponíveis:\n")
    for index, collection in enumerate(collections, start=1):
        print(f"[{index}] {collection.name}")
        print(f"    ID: {collection.id}\n")

    while True:
        raw = _read_line("Selecione uma Collection: ")
        text = raw.strip()
        if not text:
            print("Entrada inválida. Digite o número correspondente à Collection.")
            continue
        try:
            choice = int(text)
        except ValueError:
            print("Entrada inválida. Digite o número correspondente à Collection.")
            continue
        if choice < 1 or choice > len(collections):
            print(f"Opção inválida. Escolha um número entre 1 e {len(collections)}.")
            continue
        return collections[choice - 1]


def _confirm() -> bool:
    raw = _read_line("Deseja continuar? [S/n]: ")
    answer = raw.strip().lower()
    if answer in _CANCEL_VALUES:
        return False
    if answer in _CONFIRM_VALUES:
        return True
    # Entrada não reconhecida: por segurança, nunca prossegue com uma
    # atualização/geração sem confirmação inequívoca.
    print("Entrada não reconhecida.")
    return False


def _read_line(prompt: str) -> str:
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        raise _OperationCancelled() from None
