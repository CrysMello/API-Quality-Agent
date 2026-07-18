import pytest

from api_quality_agent.domain.exceptions import InvalidJsonError
from api_quality_agent.domain.models import InputOrigin, ResolvedInput
from api_quality_agent.parsers import JsonDocumentParser


def test_parses_object_root():
    result = JsonDocumentParser.parse_text('{"nome": "api", "ativo": true}')
    assert result == {"nome": "api", "ativo": True}


def test_parses_array_root():
    result = JsonDocumentParser.parse_text("[1, 2, 3]")
    assert result == [1, 2, 3]


def test_parses_nested_structures():
    text = """
    {
        "usuarios": [
            {"id": 1, "tags": ["admin", "qa"]},
            {"id": 2, "tags": []}
        ],
        "meta": {"total": 2, "pagina": {"atual": 1, "proxima": null}}
    }
    """
    result = JsonDocumentParser.parse_text(text)
    assert result["usuarios"][0]["tags"] == ["admin", "qa"]
    assert result["meta"]["pagina"]["proxima"] is None


def test_preserves_scalar_types():
    result = JsonDocumentParser.parse_text(
        '{"inteiro": 42, "decimal": 3.14, "booleano": false, "nulo": null, "texto": "valor"}'
    )
    assert result["inteiro"] == 42
    assert isinstance(result["inteiro"], int)
    assert result["decimal"] == 3.14
    assert isinstance(result["decimal"], float)
    assert result["booleano"] is False
    assert result["nulo"] is None
    assert result["texto"] == "valor"


def test_raises_invalid_json_error_with_line_and_column():
    text = "{\n  \"a\": 1,\n  \"b\": ,\n}"
    with pytest.raises(InvalidJsonError) as exc_info:
        JsonDocumentParser.parse_text(text, source_name="dados.json")

    message = str(exc_info.value)
    assert "linha 3" in message
    assert "coluna" in message
    assert "dados.json" in message


def test_parse_uses_resolved_input_content_and_name():
    resolved = ResolvedInput(
        origin=InputOrigin.INLINE, content_type="json", name="entrada-teste", content="[1, 2]"
    )
    parser = JsonDocumentParser()

    result = parser.parse(resolved)

    assert result == [1, 2]


def test_parse_error_message_includes_resolved_input_name():
    resolved = ResolvedInput(
        origin=InputOrigin.INLINE, content_type="json", name="entrada-invalida", content="{invalido"
    )
    parser = JsonDocumentParser()

    with pytest.raises(InvalidJsonError) as exc_info:
        parser.parse(resolved)

    assert "entrada-invalida" in str(exc_info.value)
