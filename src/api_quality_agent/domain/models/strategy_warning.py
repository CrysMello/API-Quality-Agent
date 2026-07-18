from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyWarning:
    code: str
    message: str
    endpoint: str | None
