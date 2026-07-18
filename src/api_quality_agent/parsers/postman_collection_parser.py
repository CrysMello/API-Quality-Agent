import copy
import json
from typing import Any

from api_quality_agent.domain.exceptions import InvalidPostmanCollectionError
from api_quality_agent.domain.models import (
    CollectionEvent,
    CollectionExample,
    CollectionFolder,
    CollectionItem,
    CollectionRequest,
    PostmanCollectionDocument,
    ResolvedInput,
    UnknownCollectionItem,
)


class PostmanCollectionParser:
    def parse(self, resolved_input: ResolvedInput) -> PostmanCollectionDocument:
        return self.parse_text(resolved_input.content, source_name=resolved_input.name)

    def parse_text(self, text: str, *, source_name: str = "<content>") -> PostmanCollectionDocument:
        document = _load_json_document(text, source_name=source_name)
        _validate_basic_structure(document, source_name=source_name)

        warnings: list[str] = []
        info = document.get("info") or {}

        items = tuple(
            _parse_item(raw_item, warnings=warnings, source_name=source_name)
            for raw_item in document.get("item", [])
        )

        return PostmanCollectionDocument(
            postman_id=info.get("_postman_id"),
            name=info["name"],
            description=info.get("description"),
            schema=info.get("schema"),
            items=items,
            variables=_copy_dict_list(document.get("variable")),
            auth=_copy_dict_or_none(document.get("auth")),
            events=_parse_events(document.get("event")),
            warnings=tuple(warnings),
        )


def _load_json_document(text: str, *, source_name: str) -> dict[str, Any]:
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidPostmanCollectionError(
            f"Collection não é um JSON válido em {source_name} "
            f"(linha {exc.lineno}, coluna {exc.colno}): {exc.msg}"
        ) from exc

    if not isinstance(document, dict):
        raise InvalidPostmanCollectionError(
            f"Collection deve ser um objeto no nível raiz: {source_name}"
        )
    return document


def _validate_basic_structure(document: dict[str, Any], *, source_name: str) -> None:
    info = document.get("info")
    if not isinstance(info, dict):
        raise InvalidPostmanCollectionError(
            f"Collection não contém 'info' válido: {source_name}"
        )
    if not isinstance(info.get("name"), str) or not info["name"]:
        raise InvalidPostmanCollectionError(
            f"'info.name' ausente ou inválido em {source_name}"
        )
    if "item" not in document or not isinstance(document["item"], list):
        raise InvalidPostmanCollectionError(
            f"Collection não contém 'item' válido: {source_name}"
        )


def _parse_item(raw_item: Any, *, warnings: list[str], source_name: str) -> CollectionItem:
    if not isinstance(raw_item, dict):
        warnings.append(
            f"Item desconhecido preservado (não é um objeto) em {source_name}: {raw_item!r}"
        )
        return UnknownCollectionItem(name=None, raw={"value": copy.deepcopy(raw_item)})

    if isinstance(raw_item.get("item"), list):
        return _parse_folder(raw_item, warnings=warnings, source_name=source_name)

    if isinstance(raw_item.get("request"), (dict, str)):
        return _parse_request(raw_item)

    warnings.append(
        f"Item desconhecido preservado em {source_name}: "
        f"{raw_item.get('name', '<sem nome>')!r}"
    )
    return UnknownCollectionItem(name=raw_item.get("name"), raw=copy.deepcopy(raw_item))


def _parse_folder(
    raw_folder: dict[str, Any], *, warnings: list[str], source_name: str
) -> CollectionFolder:
    child_items = tuple(
        _parse_item(child, warnings=warnings, source_name=source_name)
        for child in raw_folder.get("item", [])
    )
    return CollectionFolder(
        name=raw_folder.get("name"),
        description=_extract_description(raw_folder.get("description")),
        items=child_items,
        auth=_copy_dict_or_none(raw_folder.get("auth")),
        events=_parse_events(raw_folder.get("event")),
    )


def _parse_request(raw_item: dict[str, Any]) -> CollectionRequest:
    raw_request = raw_item.get("request")

    method: str | None = None
    url_value: dict[str, Any] | str | None = None
    headers: tuple[dict[str, Any], ...] = ()
    body: dict[str, Any] | None = None
    auth: dict[str, Any] | None = None
    description: str | None = None

    if isinstance(raw_request, str):
        url_value = raw_request
    elif isinstance(raw_request, dict):
        method = raw_request.get("method")
        url_value = raw_request.get("url")
        headers = _copy_dict_list(raw_request.get("header"))
        body = _copy_dict_or_none(raw_request.get("body"))
        auth = _copy_dict_or_none(raw_request.get("auth"))
        description = _extract_description(raw_request.get("description"))

    return CollectionRequest(
        item_id=raw_item.get("id"),
        name=raw_item.get("name"),
        description=description,
        method=method,
        url=copy.deepcopy(url_value),
        url_raw=_extract_url_raw(url_value),
        headers=headers,
        body=body,
        auth=auth,
        events=_parse_events(raw_item.get("event")),
        examples=_parse_examples(raw_item.get("response")),
    )


def _extract_url_raw(url_value: Any) -> str | None:
    if isinstance(url_value, str):
        return url_value
    if isinstance(url_value, dict):
        raw = url_value.get("raw")
        return raw if isinstance(raw, str) else None
    return None


def _extract_description(raw_description: Any) -> str | None:
    if isinstance(raw_description, str):
        return raw_description
    if isinstance(raw_description, dict):
        content = raw_description.get("content")
        return content if isinstance(content, str) else None
    return None


def _parse_events(raw_events: Any) -> tuple[CollectionEvent, ...]:
    if not isinstance(raw_events, list):
        return ()

    events: list[CollectionEvent] = []
    for raw_event in raw_events:
        if not isinstance(raw_event, dict):
            continue
        script = raw_event.get("script")
        script = script if isinstance(script, dict) else {}
        exec_value = script.get("exec")
        if isinstance(exec_value, list):
            exec_lines = tuple(str(line) for line in exec_value)
        elif isinstance(exec_value, str):
            exec_lines = (exec_value,)
        else:
            exec_lines = ()

        events.append(
            CollectionEvent(
                listen=raw_event.get("listen"),
                exec_lines=exec_lines,
                script_type=script.get("type"),
                raw=copy.deepcopy(raw_event),
            )
        )
    return tuple(events)


def _parse_examples(raw_responses: Any) -> tuple[CollectionExample, ...]:
    if not isinstance(raw_responses, list):
        return ()

    examples: list[CollectionExample] = []
    for raw_response in raw_responses:
        if not isinstance(raw_response, dict):
            continue
        examples.append(
            CollectionExample(
                name=raw_response.get("name"),
                status=raw_response.get("status"),
                code=raw_response.get("code"),
                headers=_copy_dict_list(raw_response.get("header")),
                body=raw_response.get("body"),
                raw=copy.deepcopy(raw_response),
            )
        )
    return tuple(examples)


def _copy_dict_or_none(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return copy.deepcopy(value)
    return None


def _copy_dict_list(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(copy.deepcopy(item) for item in value if isinstance(item, dict))
