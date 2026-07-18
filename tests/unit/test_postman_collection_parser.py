import json

import pytest

from api_quality_agent.adapters.filesystem import InputResolver
from api_quality_agent.domain.exceptions import InvalidPostmanCollectionError
from api_quality_agent.domain.models import CollectionFolder, CollectionRequest, UnknownCollectionItem
from api_quality_agent.parsers import PostmanCollectionParser


def _minimal_collection(**overrides):
    document = {
        "info": {
            "_postman_id": "abc-123",
            "name": "Minha Collection",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": [],
    }
    document.update(overrides)
    return document


def test_parses_simple_collection():
    document = _minimal_collection(
        item=[
            {
                "name": "Ping",
                "id": "req-ping",
                "request": {"method": "GET", "url": "https://api.exemplo.com/ping"},
            }
        ]
    )

    result = PostmanCollectionParser().parse_text(json.dumps(document))

    assert result.name == "Minha Collection"
    assert result.postman_id == "abc-123"
    assert result.schema == "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
    assert len(result.items) == 1
    request = result.items[0]
    assert isinstance(request, CollectionRequest)
    assert request.name == "Ping"
    assert request.item_id == "req-ping"
    assert request.method == "GET"
    assert request.url_raw == "https://api.exemplo.com/ping"


def test_parses_nested_folders_preserving_order():
    document = _minimal_collection(
        item=[
            {
                "name": "Pasta A",
                "item": [
                    {"name": "R1", "request": {"method": "GET", "url": "https://x/1"}},
                    {
                        "name": "Subpasta",
                        "item": [{"name": "R2", "request": {"method": "GET", "url": "https://x/2"}}],
                    },
                    {"name": "R3", "request": {"method": "GET", "url": "https://x/3"}},
                ],
            },
            {"name": "R0", "request": {"method": "GET", "url": "https://x/0"}},
        ]
    )

    result = PostmanCollectionParser().parse_text(json.dumps(document))

    assert len(result.items) == 2
    top_folder = result.items[0]
    assert isinstance(top_folder, CollectionFolder)
    assert top_folder.name == "Pasta A"
    assert [item.name for item in top_folder.items] == ["R1", "Subpasta", "R3"]

    sub_folder = top_folder.items[1]
    assert isinstance(sub_folder, CollectionFolder)
    assert sub_folder.items[0].name == "R2"

    assert result.items[1].name == "R0"


def test_parses_request_with_body():
    document = _minimal_collection(
        item=[
            {
                "name": "Criar pet",
                "request": {
                    "method": "POST",
                    "url": "https://api.exemplo.com/pets",
                    "body": {
                        "mode": "raw",
                        "raw": '{"name": "Rex"}',
                        "options": {"raw": {"language": "json"}},
                    },
                },
            }
        ]
    )

    result = PostmanCollectionParser().parse_text(json.dumps(document))
    request = result.items[0]

    assert request.body == {
        "mode": "raw",
        "raw": '{"name": "Rex"}',
        "options": {"raw": {"language": "json"}},
    }


def test_extracts_collection_level_variables():
    document = _minimal_collection(
        variable=[
            {"key": "baseUrl", "value": "https://api.exemplo.com"},
            {"key": "token", "value": "abc"},
        ]
    )

    result = PostmanCollectionParser().parse_text(json.dumps(document))

    assert result.variables == (
        {"key": "baseUrl", "value": "https://api.exemplo.com"},
        {"key": "token", "value": "abc"},
    )


def test_extracts_request_and_collection_level_authentication():
    document = _minimal_collection(
        auth={"type": "apikey", "apikey": [{"key": "key", "value": "X-API-Key"}]},
        item=[
            {
                "name": "Secure",
                "request": {
                    "method": "GET",
                    "url": "https://x/secure",
                    "auth": {"type": "bearer", "bearer": [{"key": "token", "value": "{{token}}"}]},
                },
            }
        ],
    )

    result = PostmanCollectionParser().parse_text(json.dumps(document))

    assert result.auth == {"type": "apikey", "apikey": [{"key": "key", "value": "X-API-Key"}]}
    assert result.items[0].auth == {
        "type": "bearer",
        "bearer": [{"key": "token", "value": "{{token}}"}],
    }


def test_preserves_pre_request_and_test_scripts_exactly():
    exec_lines = [
        "const token = pm.environment.get('token');",
        "pm.request.headers.add({key: 'Authorization', value: `Bearer ${token}`});",
    ]
    test_lines = [
        "pm.test('status is 200', function () {",
        "    pm.response.to.have.status(200);",
        "});",
    ]
    document = _minimal_collection(
        item=[
            {
                "name": "Com scripts",
                "request": {"method": "GET", "url": "https://x/y"},
                "event": [
                    {
                        "listen": "prerequest",
                        "script": {"type": "text/javascript", "exec": exec_lines},
                    },
                    {
                        "listen": "test",
                        "script": {"type": "text/javascript", "exec": test_lines},
                    },
                ],
            }
        ]
    )

    result = PostmanCollectionParser().parse_text(json.dumps(document))
    events = result.items[0].events

    pre_request = next(event for event in events if event.listen == "prerequest")
    test_event = next(event for event in events if event.listen == "test")

    assert pre_request.exec_lines == tuple(exec_lines)
    assert test_event.exec_lines == tuple(test_lines)
    assert test_event.script_type == "text/javascript"


def test_extracts_saved_examples():
    document = _minimal_collection(
        item=[
            {
                "name": "Com exemplo",
                "request": {"method": "GET", "url": "https://x/y"},
                "response": [
                    {
                        "name": "200 OK",
                        "status": "OK",
                        "code": 200,
                        "header": [{"key": "Content-Type", "value": "application/json"}],
                        "body": '{"id": 1}',
                    }
                ],
            }
        ]
    )

    result = PostmanCollectionParser().parse_text(json.dumps(document))
    examples = result.items[0].examples

    assert len(examples) == 1
    assert examples[0].name == "200 OK"
    assert examples[0].code == 200
    assert examples[0].body == '{"id": 1}'
    assert examples[0].headers == ({"key": "Content-Type", "value": "application/json"},)


def test_unknown_item_is_preserved_and_generates_warning():
    document = _minimal_collection(
        item=[
            {"name": "Item estranho", "somethingElse": True},
            {"name": "Request normal", "request": {"method": "GET", "url": "https://x/y"}},
        ]
    )

    result = PostmanCollectionParser().parse_text(json.dumps(document))

    assert isinstance(result.items[0], UnknownCollectionItem)
    assert result.items[0].name == "Item estranho"
    assert result.items[0].raw["somethingElse"] is True
    assert len(result.warnings) == 1
    assert "Item estranho" in result.warnings[0]

    assert isinstance(result.items[1], CollectionRequest)


def test_raises_for_invalid_json():
    with pytest.raises(InvalidPostmanCollectionError):
        PostmanCollectionParser().parse_text("{ isto nao e json valido")


def test_raises_for_missing_info():
    document = {"item": []}
    with pytest.raises(InvalidPostmanCollectionError):
        PostmanCollectionParser().parse_text(json.dumps(document))


def test_raises_for_missing_name():
    document = {"info": {"schema": "x"}, "item": []}
    with pytest.raises(InvalidPostmanCollectionError):
        PostmanCollectionParser().parse_text(json.dumps(document))


def test_raises_for_missing_item_list():
    document = {"info": {"name": "X"}}
    with pytest.raises(InvalidPostmanCollectionError):
        PostmanCollectionParser().parse_text(json.dumps(document))


def test_raises_for_non_object_root():
    with pytest.raises(InvalidPostmanCollectionError):
        PostmanCollectionParser().parse_text(json.dumps([1, 2, 3]))


def test_parsing_from_file_does_not_modify_original_file(tmp_path):
    document = _minimal_collection(
        item=[{"name": "Ping", "request": {"method": "GET", "url": "https://x/y"}}]
    )
    original_bytes = json.dumps(document).encode("utf-8")
    file_path = tmp_path / "collection.json"
    file_path.write_bytes(original_bytes)

    resolved = InputResolver().resolve_from_file(file_path)
    PostmanCollectionParser().parse(resolved)

    assert file_path.read_bytes() == original_bytes


def test_mutating_parsed_model_does_not_affect_new_parse():
    document = _minimal_collection(
        item=[
            {
                "name": "R",
                "request": {
                    "method": "GET",
                    "url": "https://x/y",
                    "header": [{"key": "A", "value": "1"}],
                },
            }
        ]
    )
    text = json.dumps(document)
    parser = PostmanCollectionParser()

    first = parser.parse_text(text)
    first.items[0].headers[0]["value"] = "MUTATED"

    second = parser.parse_text(text)

    assert second.items[0].headers[0]["value"] == "1"
