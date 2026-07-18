import io

import pytest

from api_quality_agent.adapters.filesystem import InputResolver
from api_quality_agent.domain.exceptions import (
    EmptyInputError,
    InputEncodingError,
    InputFileNotFoundError,
    InputSizeLimitExceededError,
    UnsupportedInputExtensionError,
)
from api_quality_agent.domain.models import InputOrigin


def test_resolve_from_file_reads_utf8_content(tmp_path):
    file_path = tmp_path / "dados.json"
    file_path.write_text('{"nome": "café"}', encoding="utf-8")

    resolver = InputResolver()
    resolved = resolver.resolve_from_file(file_path)

    assert resolved.origin == InputOrigin.FILE
    assert resolved.content_type == "json"
    assert resolved.name == str(file_path)
    assert resolved.content == '{"nome": "café"}'


def test_resolve_from_file_does_not_modify_original_file(tmp_path):
    file_path = tmp_path / "dados.json"
    original_bytes = b'{"a": 1}'
    file_path.write_bytes(original_bytes)

    InputResolver().resolve_from_file(file_path)

    assert file_path.read_bytes() == original_bytes


def test_resolve_from_file_raises_for_missing_file(tmp_path):
    missing = tmp_path / "nao-existe.json"
    with pytest.raises(InputFileNotFoundError):
        InputResolver().resolve_from_file(missing)


def test_resolve_from_file_raises_for_empty_file(tmp_path):
    empty_file = tmp_path / "vazio.json"
    empty_file.write_bytes(b"")
    with pytest.raises(EmptyInputError):
        InputResolver().resolve_from_file(empty_file)


def test_resolve_from_file_raises_for_unsupported_extension(tmp_path):
    yaml_file = tmp_path / "dados.yaml"
    yaml_file.write_text("chave: valor", encoding="utf-8")
    with pytest.raises(UnsupportedInputExtensionError):
        InputResolver().resolve_from_file(yaml_file)


def test_resolve_from_file_raises_for_invalid_encoding(tmp_path):
    file_path = tmp_path / "dados.json"
    file_path.write_bytes('{"nome": "café"}'.encode("latin-1"))
    with pytest.raises(InputEncodingError):
        InputResolver().resolve_from_file(file_path)


def test_resolve_from_file_raises_when_exceeding_size_limit(tmp_path):
    file_path = tmp_path / "grande.json"
    file_path.write_text('{"a": "01234567890123456789"}', encoding="utf-8")

    resolver = InputResolver(max_size_bytes=10)

    with pytest.raises(InputSizeLimitExceededError):
        resolver.resolve_from_file(file_path)


def test_resolve_from_file_accepts_content_within_configured_limit(tmp_path):
    file_path = tmp_path / "pequeno.json"
    file_path.write_text("{}", encoding="utf-8")

    resolver = InputResolver(max_size_bytes=1024)
    resolved = resolver.resolve_from_file(file_path)

    assert resolved.content == "{}"


def test_resolve_from_stdin_reads_provided_stream():
    stream = io.StringIO('{"origem": "stdin"}')
    resolved = InputResolver().resolve_from_stdin(stream)

    assert resolved.origin == InputOrigin.STDIN
    assert resolved.content == '{"origem": "stdin"}'


def test_resolve_from_stdin_raises_for_empty_stream():
    stream = io.StringIO("")
    with pytest.raises(EmptyInputError):
        InputResolver().resolve_from_stdin(stream)


def test_resolve_from_stdin_raises_when_exceeding_size_limit():
    stream = io.StringIO('{"a": "01234567890123456789"}')
    resolver = InputResolver(max_size_bytes=10)
    with pytest.raises(InputSizeLimitExceededError):
        resolver.resolve_from_stdin(stream)


def test_resolve_from_content_wraps_content_directly():
    resolved = InputResolver().resolve_from_content('{"a": 1}', name="teste-inline")

    assert resolved.origin == InputOrigin.INLINE
    assert resolved.name == "teste-inline"
    assert resolved.content == '{"a": 1}'


def test_resolve_from_content_raises_for_empty_string():
    with pytest.raises(EmptyInputError):
        InputResolver().resolve_from_content("")


def test_resolve_from_content_raises_when_exceeding_size_limit():
    resolver = InputResolver(max_size_bytes=5)
    with pytest.raises(InputSizeLimitExceededError):
        resolver.resolve_from_content('{"a": "01234567890123456789"}')
