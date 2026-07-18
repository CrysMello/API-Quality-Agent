import json
from typing import Any

from api_quality_agent.domain.exceptions import InvalidJsonError
from api_quality_agent.domain.models import ResolvedInput


class JsonDocumentParser:
    def parse(self, resolved_input: ResolvedInput) -> Any:
        return self.parse_text(resolved_input.content, source_name=resolved_input.name)

    @staticmethod
    def parse_text(text: str, *, source_name: str = "<content>") -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise InvalidJsonError(
                f"JSON malformado em {source_name} "
                f"(linha {exc.lineno}, coluna {exc.colno}): {exc.msg}"
            ) from exc
