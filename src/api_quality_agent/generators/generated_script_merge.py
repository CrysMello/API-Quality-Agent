from dataclasses import dataclass

from api_quality_agent.domain.models import MergeAction
from api_quality_agent.domain.services import ManagedBlockMerger
from api_quality_agent.generators.generated_test_script import GeneratedTestScript
from api_quality_agent.generators.generated_test_summary_item import GeneratedTestSummaryItem
from api_quality_agent.generators.generation_warning import GenerationWarning


@dataclass(frozen=True)
class GeneratedScriptMergeResult:
    text: str
    block_id: str
    action: MergeAction
    summary: tuple[GeneratedTestSummaryItem, ...]
    test_count: int
    warnings: tuple[GenerationWarning, ...]


def merge_generated_script(
    merger: ManagedBlockMerger,
    original_text: str,
    block_id: str,
    generated: GeneratedTestScript,
) -> GeneratedScriptMergeResult:
    # Utiliza exclusivamente o JavaScript já pronto: o merge nunca reinterpreta
    # ou reconstrói os comentários gerados pelo PostmanTestGenerator.
    result = merger.merge(original_text, block_id, generated.script)

    return GeneratedScriptMergeResult(
        text=result.text,
        block_id=result.block_id,
        action=result.action,
        summary=generated.summary,
        test_count=generated.test_count,
        warnings=generated.warnings,
    )
