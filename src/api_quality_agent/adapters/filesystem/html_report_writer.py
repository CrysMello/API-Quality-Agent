from pathlib import Path


class HtmlReportWriter:
    def write(self, *, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
