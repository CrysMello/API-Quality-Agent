from dataclasses import dataclass


@dataclass(frozen=True)
class ApprovalResult:
    approved: bool
    reason: str
