import re

from api_quality_agent.domain.exceptions import (
    CorruptedManagedBlockError,
    DuplicateManagedBlockError,
    UnclosedManagedBlockError,
)
from api_quality_agent.domain.models import ManagedBlock

_OPEN_PATTERN = re.compile(
    r'^[ \t]*//[ \t]*<api-quality-agent:block[ \t]+id="([^"]*)"[ \t]*>[ \t]*$',
    re.MULTILINE,
)
_CLOSE_PATTERN = re.compile(
    r"^[ \t]*//[ \t]*</api-quality-agent:block>[ \t]*$",
    re.MULTILINE,
)
_MARKER_KEYWORD_PATTERN = re.compile(r"api-quality-agent:block", re.IGNORECASE)

_Event = tuple[str, int, int, str | None]


class ManagedBlockParser:
    def parse(self, text: str) -> tuple[ManagedBlock, ...]:
        events = self._collect_events(text)
        self._check_for_corrupted_markers(text, events)
        blocks = self._pair_events(text, events)
        self._check_duplicates(blocks)
        return blocks

    @staticmethod
    def _collect_events(text: str) -> list[_Event]:
        events: list[_Event] = []
        for match in _OPEN_PATTERN.finditer(text):
            events.append(("open", match.start(), match.end(), match.group(1)))
        for match in _CLOSE_PATTERN.finditer(text):
            events.append(("close", match.start(), match.end(), None))
        events.sort(key=lambda event: event[1])
        return events

    @staticmethod
    def _check_for_corrupted_markers(text: str, events: list[_Event]) -> None:
        valid_spans = [(start, end) for _, start, end, _ in events]
        for match in _MARKER_KEYWORD_PATTERN.finditer(text):
            position = match.start()
            if not any(start <= position < end for start, end in valid_spans):
                raise CorruptedManagedBlockError(
                    "Marcador de bloco gerenciado malformado encontrado próximo "
                    f"à posição {position} do script."
                )

    @staticmethod
    def _pair_events(text: str, events: list[_Event]) -> tuple[ManagedBlock, ...]:
        blocks: list[ManagedBlock] = []
        pending: tuple[int, int, str] | None = None

        for kind, start, end, block_id in events:
            if kind == "open":
                if pending is not None:
                    raise UnclosedManagedBlockError(
                        f"Bloco gerenciado '{pending[2]}' não foi fechado antes de outro "
                        "marcador de abertura."
                    )
                if not block_id:
                    raise CorruptedManagedBlockError(
                        "Marcador de bloco gerenciado com identificador vazio."
                    )
                content_start = _advance_past_newline(text, end)
                pending = (start, content_start, block_id)
            else:
                if pending is None:
                    raise CorruptedManagedBlockError(
                        "Marcador de fechamento encontrado sem um bloco aberto correspondente."
                    )
                marker_start, content_start, pending_block_id = pending
                blocks.append(
                    ManagedBlock(
                        block_id=pending_block_id,
                        content=text[content_start:start],
                        block_start=marker_start,
                        content_start=content_start,
                        content_end=start,
                        block_end=_advance_past_newline(text, end),
                    )
                )
                pending = None

        if pending is not None:
            raise UnclosedManagedBlockError(f"Bloco gerenciado '{pending[2]}' não foi fechado.")

        return tuple(blocks)

    @staticmethod
    def _check_duplicates(blocks: tuple[ManagedBlock, ...]) -> None:
        seen: set[str] = set()
        for block in blocks:
            if block.block_id in seen:
                raise DuplicateManagedBlockError(
                    f"Bloco gerenciado duplicado: '{block.block_id}'."
                )
            seen.add(block.block_id)


def _advance_past_newline(text: str, position: int) -> int:
    if position < len(text) and text[position] == "\n":
        return position + 1
    return position
