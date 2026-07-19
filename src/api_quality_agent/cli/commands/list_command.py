import argparse

from api_quality_agent.cli import bootstrap


def register(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = subparsers.add_parser(
        "list", help="Lista as Collections disponíveis no Workspace ativo."
    )
    parser.set_defaults(handler=_handle_list)


def _handle_list(_args: argparse.Namespace) -> int:
    context = bootstrap.build_context()
    workspace_ref = bootstrap.resolve_active_workspace(context)

    collections = context.list_collections_use_case.execute()

    print(f"Workspace: {workspace_ref.name}\n")
    if not collections:
        print("Nenhuma Collection foi encontrada no workspace configurado.")
        return 0

    print("Collections disponíveis:\n")
    for index, collection in enumerate(bootstrap.sort_collections(collections), start=1):
        print(f"[{index}] {collection.name}")
        print(f"    ID: {collection.id}\n")

    return 0
