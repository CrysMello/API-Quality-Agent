from dataclasses import dataclass

from api_quality_agent.domain.models.merge_action import MergeAction


@dataclass(frozen=True)
class MergeResult:
    text: str
    block_id: str
    action: MergeAction
