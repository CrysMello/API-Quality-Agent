import pytest

from api_quality_agent.domain.exceptions import (
    CorruptedManagedBlockError,
    DuplicateManagedBlockError,
    UnclosedManagedBlockError,
)
from api_quality_agent.domain.services import ManagedBlockParser


def test_parses_no_blocks_from_empty_text():
    blocks = ManagedBlockParser().parse("")

    assert blocks == ()


def test_parses_no_blocks_from_manual_script():
    text = "console.log('oi');\npm.test('manual', function () {});\n"

    blocks = ManagedBlockParser().parse(text)

    assert blocks == ()


def test_parses_single_block_and_extracts_content():
    text = (
        '// <api-quality-agent:block id="auto-tests">\n'
        "pm.test('a', function () {});\n"
        "// </api-quality-agent:block>\n"
    )

    blocks = ManagedBlockParser().parse(text)

    assert len(blocks) == 1
    assert blocks[0].block_id == "auto-tests"
    assert blocks[0].content == "pm.test('a', function () {});\n"


def test_parses_multiple_blocks_independently():
    text = (
        '// <api-quality-agent:block id="a">\n'
        "A\n"
        "// </api-quality-agent:block>\n"
        "texto do meio\n"
        '// <api-quality-agent:block id="b">\n'
        "B\n"
        "// </api-quality-agent:block>\n"
    )

    blocks = ManagedBlockParser().parse(text)

    assert [b.block_id for b in blocks] == ["a", "b"]
    assert blocks[0].content == "A\n"
    assert blocks[1].content == "B\n"


def test_raises_for_duplicate_block_id():
    text = (
        '// <api-quality-agent:block id="x">\n'
        "A\n"
        "// </api-quality-agent:block>\n"
        '// <api-quality-agent:block id="x">\n'
        "B\n"
        "// </api-quality-agent:block>\n"
    )

    with pytest.raises(DuplicateManagedBlockError):
        ManagedBlockParser().parse(text)


def test_raises_for_unclosed_block():
    text = '// <api-quality-agent:block id="x">\nA\n'

    with pytest.raises(UnclosedManagedBlockError):
        ManagedBlockParser().parse(text)


def test_raises_for_second_opening_before_first_closes():
    text = (
        '// <api-quality-agent:block id="a">\n'
        "A\n"
        '// <api-quality-agent:block id="b">\n'
        "B\n"
        "// </api-quality-agent:block>\n"
    )

    with pytest.raises(UnclosedManagedBlockError):
        ManagedBlockParser().parse(text)


def test_raises_for_orphan_closing_marker():
    text = "texto\n// </api-quality-agent:block>\n"

    with pytest.raises(CorruptedManagedBlockError):
        ManagedBlockParser().parse(text)


def test_raises_for_malformed_opening_marker_without_quotes():
    text = "// <api-quality-agent:block id=x>\nA\n// </api-quality-agent:block>\n"

    with pytest.raises(CorruptedManagedBlockError):
        ManagedBlockParser().parse(text)


def test_raises_for_opening_marker_without_id():
    text = "// <api-quality-agent:block>\nA\n// </api-quality-agent:block>\n"

    with pytest.raises(CorruptedManagedBlockError):
        ManagedBlockParser().parse(text)


def test_raises_for_empty_block_id():
    text = '// <api-quality-agent:block id="">\nA\n// </api-quality-agent:block>\n'

    with pytest.raises(CorruptedManagedBlockError):
        ManagedBlockParser().parse(text)
