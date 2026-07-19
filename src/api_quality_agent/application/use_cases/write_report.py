from pathlib import Path

from api_quality_agent.domain.exceptions import ReportAlreadyExistsError
from api_quality_agent.ports.outbound import ReportWriter

_DEFAULT_REPORT_FILENAME = "report.html"


class WriteReportUseCase:
    def __init__(self, report_writer: ReportWriter) -> None:
        self._report_writer = report_writer

    def execute(
        self,
        *,
        content: str,
        source_path: str,
        output: str | None,
        overwrite: bool,
    ) -> Path:
        target_path = _resolve_output_path(source_path=source_path, output=output)

        if target_path.exists() and not overwrite:
            raise ReportAlreadyExistsError(
                f"O arquivo de relatório já existe:\n\n{target_path}\n\n"
                "Use --overwrite para substituí-lo."
            )

        self._report_writer.write(path=target_path, content=content)
        return target_path


def _resolve_output_path(*, source_path: str, output: str | None) -> Path:
    source_dir = Path(source_path).resolve().parent

    if output is None:
        # Sem --output: relatório fica ao lado do result.json de origem.
        return source_dir / _DEFAULT_REPORT_FILENAME

    output_path = Path(output)
    looks_like_directory = output_path.is_dir() or (
        not output_path.exists() and output_path.suffix == ""
    )
    if looks_like_directory:
        return output_path / f"report_{_execution_timestamp(source_dir)}.html"

    return output_path


def _execution_timestamp(source_dir: Path) -> str:
    # O nome do diretório de origem é "run_<timestamp>" (ver
    # JsonExecutionResultRepository) — reaproveitado aqui só para nomear o
    # arquivo de saída quando --output aponta para um diretório, nunca como
    # um identificador novo inventado.
    name = source_dir.name
    return name.removeprefix("run_") if name.startswith("run_") else name
