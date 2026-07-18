import pytest

from api_quality_agent.domain.exceptions import UnresolvedReferenceError
from api_quality_agent.parsers import ReferenceResolver


def test_resolves_simple_internal_reference():
    document = {
        "components": {"schemas": {"Pet": {"type": "object", "properties": {"name": {"type": "string"}}}}},
        "target": {"$ref": "#/components/schemas/Pet"},
    }
    resolver = ReferenceResolver(document)

    resolved = resolver.resolve(document["target"])

    assert resolved == {"type": "object", "properties": {"name": {"type": "string"}}}
    assert resolver.warnings == ()


def test_resolves_nested_references_recursively():
    document = {
        "components": {
            "schemas": {
                "Address": {"type": "object", "properties": {"city": {"type": "string"}}},
                "Person": {
                    "type": "object",
                    "properties": {"address": {"$ref": "#/components/schemas/Address"}},
                },
            }
        }
    }
    resolver = ReferenceResolver(document)

    resolved = resolver.resolve({"$ref": "#/components/schemas/Person"})

    assert resolved == {
        "type": "object",
        "properties": {
            "address": {"type": "object", "properties": {"city": {"type": "string"}}},
        },
    }


def test_root_pointer_resolves_to_entire_document():
    document = {"info": {"title": "x"}}
    resolver = ReferenceResolver(document)

    assert resolver.resolve({"$ref": "#/"}) == document


def test_unescapes_json_pointer_segments():
    document = {"components": {"schemas": {"a/b": {"type": "string"}, "c~d": {"type": "integer"}}}}
    resolver = ReferenceResolver(document)

    assert resolver.resolve({"$ref": "#/components/schemas/a~1b"}) == {"type": "string"}
    assert resolver.resolve({"$ref": "#/components/schemas/c~0d"}) == {"type": "integer"}


def test_raises_for_missing_internal_reference():
    document = {"components": {"schemas": {}}}
    resolver = ReferenceResolver(document)

    with pytest.raises(UnresolvedReferenceError):
        resolver.resolve({"$ref": "#/components/schemas/Missing"})


def test_external_reference_generates_warning_and_is_preserved():
    document = {"target": {"$ref": "outro-arquivo.yaml#/Foo"}}
    resolver = ReferenceResolver(document)

    resolved = resolver.resolve(document["target"])

    assert resolved == {"$ref": "outro-arquivo.yaml#/Foo"}
    assert len(resolver.warnings) == 1
    assert "outro-arquivo.yaml#/Foo" in resolver.warnings[0]


def test_circular_reference_does_not_cause_infinite_recursion():
    document = {
        "components": {
            "schemas": {
                "Node": {
                    "type": "object",
                    "properties": {
                        "children": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/Node"},
                        }
                    },
                }
            }
        }
    }
    resolver = ReferenceResolver(document)

    resolved = resolver.resolve({"$ref": "#/components/schemas/Node"})

    assert resolved["type"] == "object"
    inner_items = resolved["properties"]["children"]["items"]
    assert inner_items == {"$ref": "#/components/schemas/Node"}


def test_resolves_lists_and_leaves_scalars_untouched():
    document = {"components": {"schemas": {"X": {"type": "string"}}}}
    resolver = ReferenceResolver(document)

    resolved = resolver.resolve([1, "texto", None, {"$ref": "#/components/schemas/X"}])

    assert resolved == [1, "texto", None, {"type": "string"}]
