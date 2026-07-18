import json
from dataclasses import replace

from api_quality_agent.domain.models import CollectionEvent
from api_quality_agent.parsers import PostmanCollectionParser, PostmanCollectionSerializer


def _parse(document: dict) -> object:
    return PostmanCollectionParser().parse_text(json.dumps(document))


def test_round_trip_preserves_name_description_and_schema():
    document = _parse(
        {
            "info": {
                "name": "Minha Collection",
                "description": "Descrição da Collection",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": [],
        }
    )

    serialized = PostmanCollectionSerializer().serialize(document)

    assert serialized["info"]["name"] == "Minha Collection"
    assert serialized["info"]["description"] == "Descrição da Collection"
    assert serialized["info"]["schema"] == document.schema
    assert serialized["item"] == []


def test_round_trip_preserves_request_method_url_headers_and_body():
    document = _parse(
        {
            "info": {
                "name": "Col",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": [
                {
                    "name": "Criar pet",
                    "id": "r1",
                    "request": {
                        "method": "POST",
                        "url": {"raw": "https://x/pets", "host": ["x"], "path": ["pets"]},
                        "header": [{"key": "Content-Type", "value": "application/json"}],
                        "body": {"mode": "raw", "raw": '{"name": "Rex"}'},
                    },
                }
            ],
        }
    )

    serialized = PostmanCollectionSerializer().serialize(document)

    request_item = serialized["item"][0]
    assert request_item["id"] == "r1"
    assert request_item["name"] == "Criar pet"
    assert request_item["request"]["method"] == "POST"
    assert request_item["request"]["url"] == {
        "raw": "https://x/pets",
        "host": ["x"],
        "path": ["pets"],
    }
    assert request_item["request"]["header"] == [
        {"key": "Content-Type", "value": "application/json"}
    ]
    assert request_item["request"]["body"] == {"mode": "raw", "raw": '{"name": "Rex"}'}


def test_round_trip_preserves_nested_folders():
    document = _parse(
        {
            "info": {
                "name": "Col",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": [
                {
                    "name": "Pasta",
                    "item": [
                        {"name": "Ping", "request": {"method": "GET", "url": "https://x/y"}}
                    ],
                }
            ],
        }
    )

    serialized = PostmanCollectionSerializer().serialize(document)

    folder = serialized["item"][0]
    assert folder["name"] == "Pasta"
    assert folder["item"][0]["name"] == "Ping"
    assert folder["item"][0]["request"]["method"] == "GET"


def test_round_trip_preserves_examples_as_raw():
    document = _parse(
        {
            "info": {
                "name": "Col",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": [
                {
                    "name": "Ping",
                    "request": {"method": "GET", "url": "https://x/y"},
                    "response": [
                        {
                            "name": "ok",
                            "status": "OK",
                            "code": 200,
                            "header": [],
                            "body": "{}",
                        }
                    ],
                }
            ],
        }
    )

    serialized = PostmanCollectionSerializer().serialize(document)

    assert serialized["item"][0]["response"] == [
        {"name": "ok", "status": "OK", "code": 200, "header": [], "body": "{}"}
    ]


def test_serializer_uses_event_raw_field_so_merged_managed_blocks_round_trip():
    document = _parse(
        {
            "info": {
                "name": "Col",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": [{"name": "Ping", "request": {"method": "GET", "url": "https://x/y"}}],
        }
    )
    request = document.items[0]
    merged_event = CollectionEvent(
        listen="test",
        exec_lines=("// bloco gerenciado", "pm.response.to.have.status(200);"),
        script_type="text/javascript",
        raw={
            "listen": "test",
            "script": {
                "type": "text/javascript",
                "exec": ["// bloco gerenciado", "pm.response.to.have.status(200);"],
            },
        },
    )
    updated_request = replace(request, events=(merged_event,))
    updated_document = replace(document, items=(updated_request,))

    serialized = PostmanCollectionSerializer().serialize(updated_document)

    event = serialized["item"][0]["event"][0]
    assert event["listen"] == "test"
    assert event["script"]["exec"] == [
        "// bloco gerenciado",
        "pm.response.to.have.status(200);",
    ]


def test_unknown_item_is_preserved_verbatim():
    document = _parse(
        {
            "info": {
                "name": "Col",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": [{"name": "Algo estranho", "unsupported_kind": True}],
        }
    )

    serialized = PostmanCollectionSerializer().serialize(document)

    assert serialized["item"][0] == {"name": "Algo estranho", "unsupported_kind": True}
