from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedHeader:
    key: str | None
    value: str | None
    disabled: bool = False
