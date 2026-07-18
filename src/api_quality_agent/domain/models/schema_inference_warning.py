from dataclasses import dataclass


@dataclass(frozen=True)
class SchemaInferenceWarning:
    code: str
    message: str
    path: str
