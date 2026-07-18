from api_quality_agent.domain.models import ManagedBlock, MergeAction, MergeResult
from api_quality_agent.domain.policies import ensure_non_empty_id
from api_quality_agent.domain.services.managed_block_parser import ManagedBlockParser

_OPEN_TEMPLATE = '// <api-quality-agent:block id="{block_id}">\n'
_CLOSE_LINE = "// </api-quality-agent:block>\n"


class ManagedBlockMerger:
    def __init__(self, parser: ManagedBlockParser | None = None) -> None:
        self._parser = parser or ManagedBlockParser()

    def merge(self, original_text: str, block_id: str, new_content: str) -> MergeResult:
        ensure_non_empty_id(block_id, "block_id")
        blocks = self._parser.parse(original_text)

        existing = next((block for block in blocks if block.block_id == block_id), None)

        if existing is not None:
            new_text = _replace_block_content(original_text, existing, new_content)
            action = MergeAction.REPLACED
        else:
            new_text = _insert_block(original_text, block_id, new_content)
            action = MergeAction.INSERTED

        return MergeResult(text=new_text, block_id=block_id, action=action)


def _normalize_content(content: str) -> str:
    return content if content.endswith("\n") else content + "\n"


def _replace_block_content(original_text: str, block: ManagedBlock, new_content: str) -> str:
    normalized_content = _normalize_content(new_content)
    return (
        original_text[: block.content_start]
        + normalized_content
        + original_text[block.content_end :]
    )


def _insert_block(original_text: str, block_id: str, new_content: str) -> str:
    normalized_content = _normalize_content(new_content)
    block_text = _OPEN_TEMPLATE.format(block_id=block_id) + normalized_content + _CLOSE_LINE

    if not original_text.strip():
        return block_text

    return f"{original_text.rstrip(chr(10))}\n\n{block_text}"
