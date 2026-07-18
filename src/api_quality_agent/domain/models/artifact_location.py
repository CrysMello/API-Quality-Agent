from dataclasses import dataclass


@dataclass(frozen=True)
class ArtifactLocation:
    path: str
