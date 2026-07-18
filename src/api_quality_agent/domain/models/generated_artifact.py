from dataclasses import dataclass


@dataclass(frozen=True)
class GeneratedArtifact:
    category: str
    relative_path: str
    content: str
