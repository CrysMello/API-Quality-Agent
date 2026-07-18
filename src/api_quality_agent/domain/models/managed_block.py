from dataclasses import dataclass


@dataclass(frozen=True)
class ManagedBlock:
    block_id: str
    content: str
    block_start: int
    content_start: int
    content_end: int
    block_end: int
