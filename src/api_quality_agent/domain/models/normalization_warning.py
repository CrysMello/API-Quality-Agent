from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizationWarning:
    code: str
    message: str
    field: str | None
    request_id: str | None
