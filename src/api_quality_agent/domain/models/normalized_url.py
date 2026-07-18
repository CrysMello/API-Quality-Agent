from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedQueryParameter:
    key: str | None
    value: str | None
    disabled: bool = False


@dataclass(frozen=True)
class NormalizedUrlVariable:
    key: str | None
    value: str | None


@dataclass(frozen=True)
class NormalizedUrl:
    raw: str | None
    protocol: str | None
    host: tuple[str, ...]
    path: tuple[str, ...]
    query_parameters: tuple[NormalizedQueryParameter, ...]
    variables: tuple[NormalizedUrlVariable, ...]
