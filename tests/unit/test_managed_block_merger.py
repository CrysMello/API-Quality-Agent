import pytest

from api_quality_agent.domain.exceptions import (
    CorruptedManagedBlockError,
    DuplicateManagedBlockError,
    UnclosedManagedBlockError,
)
from api_quality_agent.domain.models import MergeAction
from api_quality_agent.domain.services import ManagedBlockMerger


# --- Script vazio --------------------------------------------------------------


def test_merge_into_empty_script_inserts_block():
    result = ManagedBlockMerger().merge("", "auto-tests", "pm.test('a', function () {});")

    assert result.action == MergeAction.INSERTED
    assert result.text == (
        '// <api-quality-agent:block id="auto-tests">\n'
        "pm.test('a', function () {});\n"
        "// </api-quality-agent:block>\n"
    )


# --- Script manual ---------------------------------------------------------------


def test_merge_into_manual_script_preserves_manual_code():
    manual_script = "// script manual do usuário\nconsole.log('oi');\n"

    result = ManagedBlockMerger().merge(manual_script, "auto-tests", "pm.test('a', function () {});")

    assert result.action == MergeAction.INSERTED
    assert result.text.startswith(manual_script)
    assert 'id="auto-tests"' in result.text
    assert "pm.test('a', function () {});" in result.text


def test_merge_does_not_alter_manual_script_without_trailing_newline():
    manual_script = "console.log('sem quebra final')"

    result = ManagedBlockMerger().merge(manual_script, "auto-tests", "pm.test('a', function () {});")

    assert result.text.startswith("console.log('sem quebra final')")


# --- Bloco existente ---------------------------------------------------------------


def test_merge_replaces_existing_block_content_only():
    original = (
        "// código manual antes\n"
        '// <api-quality-agent:block id="auto-tests">\n'
        "pm.test('antigo', function () {});\n"
        "// </api-quality-agent:block>\n"
        "// código manual depois\n"
    )

    result = ManagedBlockMerger().merge(original, "auto-tests", "pm.test('novo', function () {});")

    assert result.action == MergeAction.REPLACED
    assert "código manual antes" in result.text
    assert "código manual depois" in result.text
    assert "pm.test('antigo'" not in result.text
    assert "pm.test('novo'" in result.text


# --- Múltiplos blocos ---------------------------------------------------------------


def test_merge_only_affects_targeted_block_among_multiple():
    original = (
        '// <api-quality-agent:block id="a">\n'
        "A\n"
        "// </api-quality-agent:block>\n"
        "texto do meio preservado\n"
        '// <api-quality-agent:block id="b">\n'
        "B\n"
        "// </api-quality-agent:block>\n"
    )

    result = ManagedBlockMerger().merge(original, "b", "B2")

    assert "A\n// </api-quality-agent:block>" in result.text
    assert "texto do meio preservado" in result.text
    assert "B2" in result.text
    assert "\nB\n" not in result.text


def test_merge_inserts_new_block_after_existing_ones():
    original = (
        '// <api-quality-agent:block id="a">\n'
        "A\n"
        "// </api-quality-agent:block>\n"
    )

    result = ManagedBlockMerger().merge(original, "b", "B")

    assert result.action == MergeAction.INSERTED
    assert 'id="a"' in result.text
    assert 'id="b"' in result.text
    assert result.text.index('id="a"') < result.text.index('id="b"')


# --- Bloco duplicado ---------------------------------------------------------------


def test_merge_raises_for_duplicate_block_in_original_text():
    original = (
        '// <api-quality-agent:block id="x">\n'
        "A\n"
        "// </api-quality-agent:block>\n"
        '// <api-quality-agent:block id="x">\n'
        "B\n"
        "// </api-quality-agent:block>\n"
    )

    with pytest.raises(DuplicateManagedBlockError):
        ManagedBlockMerger().merge(original, "x", "C")


# --- Bloco sem fechamento ---------------------------------------------------------------


def test_merge_raises_for_unclosed_block_and_preserves_original_reference():
    original = '// <api-quality-agent:block id="x">\nA\n'

    with pytest.raises(UnclosedManagedBlockError):
        ManagedBlockMerger().merge(original, "x", "B")

    # a entrada não é mutável; nada foi escrito/perdido
    assert original == '// <api-quality-agent:block id="x">\nA\n'


def test_merge_raises_for_corrupted_marker_without_modifying_anything():
    original = "// <api-quality-agent:block id=x>\nA\n// </api-quality-agent:block>\n"

    with pytest.raises(CorruptedManagedBlockError):
        ManagedBlockMerger().merge(original, "x", "B")


# --- Idempotência ---------------------------------------------------------------


def test_merge_is_idempotent_when_applied_twice_with_same_content():
    manual_script = "// manual\n"
    merger = ManagedBlockMerger()

    first = merger.merge(manual_script, "auto-tests", "pm.test('a', function () {});")
    second = merger.merge(first.text, "auto-tests", "pm.test('a', function () {});")

    assert first.text == second.text
    assert second.action == MergeAction.REPLACED


def test_merge_is_idempotent_across_three_applications_with_changing_content():
    text = ""
    merger = ManagedBlockMerger()

    text = merger.merge(text, "auto-tests", "pm.test('v1', function () {});").text
    text = merger.merge(text, "auto-tests", "pm.test('v2', function () {});").text
    result_a = merger.merge(text, "auto-tests", "pm.test('v3', function () {});")
    result_b = merger.merge(result_a.text, "auto-tests", "pm.test('v3', function () {});")

    assert result_a.text == result_b.text


# --- Preservação byte a byte do conteúdo externo ---------------------------------------


def test_content_outside_block_is_preserved_byte_for_byte():
    before = "// linha manual 1\n// linha manual 2 com espaços   \n"
    after = "\n// comentário final do usuário\n"
    original = (
        before
        + '// <api-quality-agent:block id="auto-tests">\n'
        + "pm.test('antigo', function () {});\n"
        + "// </api-quality-agent:block>\n"
        + after
    )

    result = ManagedBlockMerger().merge(original, "auto-tests", "pm.test('novo', function () {});")

    prefix_end = result.text.index('// <api-quality-agent:block id="auto-tests">')
    suffix_start = result.text.index("// </api-quality-agent:block>\n") + len(
        "// </api-quality-agent:block>\n"
    )

    assert result.text[:prefix_end] == before
    assert result.text[suffix_start:] == after


def test_block_markers_are_preserved_exactly_when_replacing():
    original = (
        '// <api-quality-agent:block id="auto-tests">\n'
        "old content\n"
        "// </api-quality-agent:block>\n"
    )

    result = ManagedBlockMerger().merge(original, "auto-tests", "new content")

    assert result.text.startswith('// <api-quality-agent:block id="auto-tests">\n')
    assert result.text.endswith("// </api-quality-agent:block>\n")
