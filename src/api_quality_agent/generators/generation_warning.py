from dataclasses import dataclass


@dataclass(frozen=True)
class GenerationWarning:
    code: str
    message: str
    test_id: str | None
    field: str | None
