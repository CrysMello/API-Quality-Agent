from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisWarning:
    code: str
    message: str
    endpoint: str | None
