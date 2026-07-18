from api_quality_agent.domain.models import EndpointAnalysis, MergeAction
from api_quality_agent.domain.services import ManagedBlockMerger, TestStrategyEngine
from api_quality_agent.generators import PostmanTestGenerator, merge_generated_script


def _build_endpoint() -> EndpointAnalysis:
    return EndpointAnalysis(
        source="GET /pets",
        method="GET",
        path="/pets",
        operation_id=None,
        parameters=(),
        has_request_body=False,
        request_content_types=(),
        response_status_codes=("200",),
        response_content_types=(),
        auth_type=None,
        variables_used=(),
        has_examples=False,
        example_count=0,
    )


def _generate_script():
    strategy = TestStrategyEngine().build_strategy(_build_endpoint())
    return PostmanTestGenerator().generate(strategy)


def test_merge_generated_script_uses_only_the_script_field():
    generated = _generate_script()
    merger = ManagedBlockMerger()

    result = merge_generated_script(merger, "// manual\n", "auto-tests", generated)

    assert result.action == MergeAction.INSERTED
    assert generated.script.strip() in result.text
    assert "// manual" in result.text


def test_merge_generated_script_preserves_summary_test_count_and_warnings():
    generated = _generate_script()
    merger = ManagedBlockMerger()

    result = merge_generated_script(merger, "", "auto-tests", generated)

    assert result.summary == generated.summary
    assert result.test_count == generated.test_count
    assert result.warnings == generated.warnings


def test_merge_generated_script_does_not_duplicate_comments_on_replace():
    generated = _generate_script()
    merger = ManagedBlockMerger()

    first = merge_generated_script(merger, "", "auto-tests", generated)
    second = merge_generated_script(merger, first.text, "auto-tests", generated)

    assert second.action == MergeAction.REPLACED
    assert first.text == second.text
    assert second.text.count("// Validação:") == first.text.count("// Validação:")
