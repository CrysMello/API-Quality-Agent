import argparse

from api_quality_agent.application.orchestration import CollectionGenerationResult
from api_quality_agent.cli import bootstrap, collection_selection
from api_quality_agent.cli.exit_codes import OPERATION_CANCELLED, SUCCESS
from api_quality_agent.cli.interactive import OperationCancelled, confirm
from api_quality_agent.domain.exceptions import InputError


def register(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = subparsers.add_parser(
        "generate", help="Gera e aplica testes na Collection selecionada."
    )
    collection_selection.add_selection_arguments(parser)
    parser.add_argument(
        "-f",
        "--file",
        dest="file",
        default=None,
        metavar="COLLECTION_JSON",
        help=(
            "Gera os testes a partir de uma Collection exportada localmente "
            "(arquivo .json), sem conectar à API do Postman."
        ),
    )
    parser.add_argument(
        "--openapi-file",
        dest="openapi_file",
        default=None,
        metavar="OPENAPI_JSON",
        help=(
            "Gera uma Collection completa (com testes já embutidos) a partir de "
            "uma especificação OpenAPI/Swagger local, sem conectar à API do Postman."
        ),
    )
    parser.add_argument(
        "--contract-file",
        dest="contract_file",
        default=None,
        metavar="CONTRATO_XLSX",
        help=(
            "Usa um contrato de API declarado numa planilha Excel (.xlsx) como "
            "fonte de schema para as requests pareadas, em vez de inferir só "
            "de Examples salvos. Combinável com a seleção normal da Collection "
            "ou com --file; endpoints sem contrato declarado continuam usando "
            "a inferência de sempre."
        ),
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
    collection_selection.validate_selection_arguments(args, extra_fields=("file", "openapi_file"))
    if args.contract_file is not None and args.openapi_file is not None:
        raise InputError("--contract-file não pode ser combinado com --openapi-file.")

    if args.file is not None:
        return _handle_generate_from_file(args)

    if args.openapi_file is not None:
        return _handle_generate_from_openapi_file(args)

    context = bootstrap.build_context()
    workspace_ref = bootstrap.resolve_active_workspace(context)

    try:
        selected = collection_selection.select_collection(context, workspace_ref.id, args)

        print(f"Workspace: {workspace_ref.name}")
        print(f"Collection selecionada: {selected.name}")
        print(f"Collection ID: {selected.id}\n")

        if not args.yes and not confirm():
            print("Operação cancelada pelo usuário.")
            return OPERATION_CANCELLED
    except OperationCancelled:
        print("Operação cancelada pelo usuário.")
        return OPERATION_CANCELLED

    print(f"\nCollection selecionada:\n{selected.name}\n")
    print("Gerando testes...")

    # collection_id é sempre passado explicitamente: a Collection já foi
    # resolvida acima (por ID, nome, índice ou interativamente) — isso é
    # sempre uma seleção temporária (ResolveCollectionUseCase nunca
    # persiste), nunca altera a seleção ativa salva em disco.
    if args.contract_file is not None:
        result = context.generate_with_contract_use_case.execute_online(
            contract_file=args.contract_file, collection_id=selected.id
        )
    else:
        result = context.generate_use_case.execute(collection_id=selected.id)

    _print_generation_summary(result)
    return SUCCESS


def _handle_generate_from_file(args: argparse.Namespace) -> int:
    context = bootstrap.build_offline_context()

    resolved_input = context.input_resolver.resolve_from_file(args.file)
    document = context.collection_parser.parse(resolved_input)

    print(f"Arquivo: {args.file}")
    print(f"Collection: {document.name}\n")

    try:
        if not args.yes and not confirm():
            print("Operação cancelada pelo usuário.")
            return OPERATION_CANCELLED
    except OperationCancelled:
        print("Operação cancelada pelo usuário.")
        return OPERATION_CANCELLED

    print("Gerando testes (modo local, sem conexão com a API do Postman)...")
    if args.contract_file is not None:
        result = context.generate_with_contract_use_case.execute_offline(
            contract_file=args.contract_file, document=document
        )
    else:
        result = context.generate_from_file_use_case.execute(document=document)

    _print_generation_summary(result)
    return SUCCESS


def _handle_generate_from_openapi_file(args: argparse.Namespace) -> int:
    context = bootstrap.build_offline_context()

    resolved_input = context.input_resolver.resolve_from_file(args.openapi_file)
    specification = context.openapi_parser.parse(resolved_input)

    print(f"Arquivo: {args.openapi_file}")
    print(f"Especificação: {specification.title or specification.spec_type.value}\n")

    try:
        if not args.yes and not confirm():
            print("Operação cancelada pelo usuário.")
            return OPERATION_CANCELLED
    except OperationCancelled:
        print("Operação cancelada pelo usuário.")
        return OPERATION_CANCELLED

    print("Gerando Collection e testes a partir da especificação OpenAPI (modo local)...")
    result = context.generate_from_openapi_use_case.execute(specification=specification)

    _print_generation_summary(result)
    return SUCCESS


def _print_generation_summary(result: CollectionGenerationResult) -> None:
    print("Processo concluído com sucesso.\n")
    print(f"Endpoints processados: {len(result.endpoint_outcomes)}")
    failed_outcomes = [outcome for outcome in result.endpoint_outcomes if outcome.error is not None]
    if failed_outcomes:
        print(f"  Com falha: {len(failed_outcomes)}")
    print(f"Diff possui mudanças: {result.diff.has_changes}")
    print(f"Artefatos salvos: {len(result.artifact_locations)}")
    for location in result.artifact_locations:
        print(f"  - {location.path}")
