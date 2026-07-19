from pathlib import Path

import pytest

from api_quality_agent.application.use_cases import WriteReportUseCase
from api_quality_agent.domain.exceptions import ReportAlreadyExistsError


class _CapturingWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, str]] = []

    def write(self, *, path: Path, content: str) -> None:
        self.calls.append((path, content))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def test_default_output_is_next_to_source_file(tmp_path):
    source = tmp_path / "run_20260720_103512" / "result.json"
    source.parent.mkdir(parents=True)
    source.write_text("{}", encoding="utf-8")
    writer = _CapturingWriter()
    use_case = WriteReportUseCase(writer)

    output_path = use_case.execute(
        content="<html></html>", source_path=str(source), output=None, overwrite=False
    )

    assert output_path == source.parent / "report.html"
    assert output_path.read_text(encoding="utf-8") == "<html></html>"


def test_output_as_existing_directory_uses_timestamped_filename(tmp_path):
    source = tmp_path / "run_20260720_103512123456" / "result.json"
    source.parent.mkdir(parents=True)
    source.write_text("{}", encoding="utf-8")
    output_dir = tmp_path / "reports"
    output_dir.mkdir()
    writer = _CapturingWriter()
    use_case = WriteReportUseCase(writer)

    output_path = use_case.execute(
        content="<html></html>", source_path=str(source), output=str(output_dir), overwrite=False
    )

    assert output_path == output_dir / "report_20260720_103512123456.html"


def test_output_as_nonexistent_directory_like_path_is_created(tmp_path):
    source = tmp_path / "run_20260720_103512" / "result.json"
    source.parent.mkdir(parents=True)
    source.write_text("{}", encoding="utf-8")
    output_dir = tmp_path / "reports"  # não existe ainda, sem sufixo -> tratado como diretório
    writer = _CapturingWriter()
    use_case = WriteReportUseCase(writer)

    output_path = use_case.execute(
        content="<html></html>", source_path=str(source), output=str(output_dir), overwrite=False
    )

    assert output_path.parent == output_dir
    assert output_path.read_text(encoding="utf-8") == "<html></html>"


def test_output_as_explicit_file_path_is_used_verbatim(tmp_path):
    source = tmp_path / "run_20260720_103512" / "result.json"
    source.parent.mkdir(parents=True)
    source.write_text("{}", encoding="utf-8")
    output_file = tmp_path / "meu_relatorio.html"
    writer = _CapturingWriter()
    use_case = WriteReportUseCase(writer)

    output_path = use_case.execute(
        content="<html></html>", source_path=str(source), output=str(output_file), overwrite=False
    )

    assert output_path == output_file


def test_does_not_overwrite_existing_file_without_flag(tmp_path):
    source = tmp_path / "run_20260720_103512" / "result.json"
    source.parent.mkdir(parents=True)
    source.write_text("{}", encoding="utf-8")
    existing_report = source.parent / "report.html"
    existing_report.write_text("conteúdo antigo", encoding="utf-8")
    writer = _CapturingWriter()
    use_case = WriteReportUseCase(writer)

    with pytest.raises(ReportAlreadyExistsError):
        use_case.execute(
            content="<html>novo</html>", source_path=str(source), output=None, overwrite=False
        )

    # Nada foi escrito: o conteúdo antigo permanece intocado.
    assert existing_report.read_text(encoding="utf-8") == "conteúdo antigo"
    assert writer.calls == []


def test_overwrites_existing_file_with_flag(tmp_path):
    source = tmp_path / "run_20260720_103512" / "result.json"
    source.parent.mkdir(parents=True)
    source.write_text("{}", encoding="utf-8")
    existing_report = source.parent / "report.html"
    existing_report.write_text("conteúdo antigo", encoding="utf-8")
    writer = _CapturingWriter()
    use_case = WriteReportUseCase(writer)

    output_path = use_case.execute(
        content="<html>novo</html>", source_path=str(source), output=None, overwrite=True
    )

    assert output_path.read_text(encoding="utf-8") == "<html>novo</html>"
