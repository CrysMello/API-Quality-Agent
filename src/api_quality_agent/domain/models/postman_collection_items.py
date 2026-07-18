from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CollectionEvent:
    listen: str | None
    exec_lines: tuple[str, ...]
    script_type: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class CollectionExample:
    name: str | None
    status: str | None
    code: int | None
    headers: tuple[dict[str, Any], ...]
    body: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class UnknownCollectionItem:
    name: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class CollectionRequest:
    item_id: str | None
    name: str | None
    description: str | None
    method: str | None
    url: dict[str, Any] | str | None
    url_raw: str | None
    headers: tuple[dict[str, Any], ...]
    body: dict[str, Any] | None
    auth: dict[str, Any] | None
    events: tuple[CollectionEvent, ...]
    examples: tuple[CollectionExample, ...]


@dataclass(frozen=True)
class CollectionFolder:
    name: str | None
    description: str | None
    items: tuple[CollectionItem, ...]
    auth: dict[str, Any] | None
    events: tuple[CollectionEvent, ...]


CollectionItem = CollectionFolder | CollectionRequest | UnknownCollectionItem
