from dataclasses import dataclass


@dataclass(frozen=True)
class ParameterAnalysis:
    name: str
    location: str
    required: bool
