import argparse
from pathlib import Path

from api_quality_agent.cli import bootstrap
from api_quality_agent.cli.exit_codes import OPERATION_CANCELLED, SUCCESS
from api_quality_agent.domain.models import ExecutionResultRecord


def register(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = subparsers.add_parser(
        "report",
        help="Gera um relatório HTML a partir de um result.json produzido pelo run.",
    )
    parser.add_argument(
        "-i",
        "--input",
        dest="input",
        default=None,
        metavar="RESULT_JSON",
        help=(
            "Caminho de um result.json específico. Sem esta flag, usa o "
            "resultado mais recente encontrado em artifacts/."
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output",
        default=None,
        metavar="CAMINHO",
        help=(
            "Diretório ou caminho de arquivo para o relatório. Sem esta "
            "flag, o relatório fica ao lado do result.json de origem."
        ),
    )
    parser.add_argument(
        "--format",
        dest="format",
        default="html",
        choices=["html"],
        help='Formato do relatório (só "html" nesta versão).',
    )
    parser.add_argument(
        "--overwrite",
        dest="overwrite",
        action="store_true",
        help="Substitui o arquivo de relatório caso já exista.",
    )
    parser.set_defaults(handler=_handle_report)


def _handle_report(args: argparse.Namespace) -> int:
    context = bootstrap.build_report_context()

    try:
        record = context.load_execution_result_use_case.execute(input_path=args.input)

        if args.input is None:
            print(f"Using latest execution result:\n\n  {record.source_path}\n")

        html_content = context.report_engine.render_execution_summary_html(record)

        output_path = context.write_report_use_case.execute(
            content=html_content,
            source_path=record.source_path,
            output=args.output,
            overwrite=args.overwrite,
        )
    except KeyboardInterrupt:
        print("Operação cancelada pelo usuário.")
        return OPERATION_CANCELLED

    _print_success(record, output_path)
    return SUCCESS


def _print_success(record: ExecutionResultRecord, output_path: Path) -> None:
    print("Report generated successfully.\n")
    print(f"Input:\n  {record.source_path}\n")
    print(f"Output:\n  {output_path}\n")
    print(f"Execution status:\n  {_execution_status(record)}")


def _execution_status(record: ExecutionResultRecord) -> str:
    if record.infrastructure_failure is not None:
        return "INFRASTRUCTURE FAILURE"
    return "PASSED" if record.success else "FAILED"
