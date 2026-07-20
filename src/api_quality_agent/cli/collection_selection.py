"""Seleção de Collection compartilhada entre os comandos generate e update:
por ID, nome, índice (na mesma ordenação usada por `list`) ou interativamente.
Nenhuma persistência ocorre aqui — é sempre uma seleção temporária.
"""

import argparse

from api_quality_agent.cli import bootstrap
from api_quality_agent.cli.bootstrap import CliContext
from api_quality_agent.cli.interactive import read_line
from api_quality_agent.domain.exceptions import AmbiguousResourceError, InputError, ResourceNotFoundError
from api_quality_agent.domain.models import CollectionRef


def add_selection_arguments(parser: argparse.ArgumentParser) -> None:
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


_EXTRA_FIELD_LABELS = {
    "file": "--file",
    "openapi_file": "--openapi-file",
}


def validate_selection_arguments(
    args: argparse.Namespace, *, extra_fields: tuple[str, ...] = ()
) -> None:
    fields = ("index", "collection_id", "collection_name", *extra_fields)
    provided = [getattr(args, field) is not None for field in fields]
    if sum(provided) > 1:
        options = "ID, nome ou índice"
        if extra_fields:
            extra_labels = ", ".join(_EXTRA_FIELD_LABELS.get(field, field) for field in extra_fields)
            options = f"ID, nome, índice ou {extra_labels}"
        raise InputError(
            f"informe somente uma forma de seleção da Collection. Use {options} "
            "(não podem ser combinados)."
        )


def select_collection(
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
        raise ResourceNotFoundError("Nenhuma Collection foi encontrada no workspace configurado.")
    if index < 1 or index > len(collections):
        raise InputError(
            f"opção {index} inválida. Existem {len(collections)} Collections disponíveis."
        )
    return collections[index - 1]


def _select_interactively(context: CliContext, workspace_id: str) -> CollectionRef:
    collections = bootstrap.sort_collections(context.collection_repository.list(workspace_id))
    if not collections:
        raise ResourceNotFoundError("Nenhuma Collection foi encontrada no workspace configurado.")

    print("Collections disponíveis:\n")
    for index, collection in enumerate(collections, start=1):
        print(f"[{index}] {collection.name}")
        print(f"    ID: {collection.id}\n")

    while True:
        raw = read_line("Selecione uma Collection: ")
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
