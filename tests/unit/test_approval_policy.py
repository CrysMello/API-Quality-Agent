from api_quality_agent.domain.models import (
    DiffCategory,
    DiffChangeType,
    DiffEntry,
    DiffResult,
    DiffRiskLevel,
)
from api_quality_agent.domain.services import ApprovalPolicy


def _entry(change_type, risk, category=DiffCategory.VARIABLE) -> DiffEntry:
    return DiffEntry(
        change_type=change_type,
        category=category,
        target="variable:x",
        risk=risk,
        description="alteração de teste",
    )


def _diff_with(*entries) -> DiffResult:
    return DiffResult(entries=tuple(entries))


# --- Sem diferenças / nada a aprovar ----------------------------------------------


def test_no_changes_is_trivially_approved():
    empty_diff = _diff_with()

    result = ApprovalPolicy().evaluate(empty_diff)

    assert result.approved is True


def test_no_changes_is_approved_even_without_yes_or_with_dry_run():
    empty_diff = _diff_with()

    result = ApprovalPolicy(dry_run=True).evaluate(empty_diff)

    assert result.approved is True


# --- Aprovação negada --------------------------------------------------------------


def test_approval_denied_without_explicit_yes():
    diff = _diff_with(_entry(DiffChangeType.MODIFIED, DiffRiskLevel.MEDIUM))

    result = ApprovalPolicy().evaluate(diff)

    assert result.approved is False
    assert "--yes" in result.reason or "expl" in result.reason.lower()


def test_approval_is_never_presumed_by_default_policy():
    diff = _diff_with(_entry(DiffChangeType.ADDED, DiffRiskLevel.LOW))

    result = ApprovalPolicy().evaluate(diff)

    assert result.approved is False


# --- Aprovação explícita -----------------------------------------------------------


def test_explicit_yes_approves_non_removal_changes():
    diff = _diff_with(_entry(DiffChangeType.MODIFIED, DiffRiskLevel.MEDIUM))

    result = ApprovalPolicy(explicit_yes=True).evaluate(diff)

    assert result.approved is True


def test_explicit_yes_alone_does_not_approve_removals():
    diff = _diff_with(_entry(DiffChangeType.REMOVED, DiffRiskLevel.HIGH))

    result = ApprovalPolicy(explicit_yes=True).evaluate(diff)

    assert result.approved is False


def test_explicit_yes_with_allow_removals_approves_removal_changes():
    diff = _diff_with(_entry(DiffChangeType.REMOVED, DiffRiskLevel.HIGH))

    result = ApprovalPolicy(explicit_yes=True, allow_removals=True).evaluate(diff)

    assert result.approved is True


# --- Dry-run -----------------------------------------------------------------------


def test_dry_run_always_blocks_write_even_with_explicit_yes():
    diff = _diff_with(_entry(DiffChangeType.MODIFIED, DiffRiskLevel.MEDIUM))

    result = ApprovalPolicy(dry_run=True, explicit_yes=True).evaluate(diff)

    assert result.approved is False
    assert "dry-run" in result.reason.lower()


def test_dry_run_blocks_even_when_removals_are_allowed():
    diff = _diff_with(_entry(DiffChangeType.REMOVED, DiffRiskLevel.HIGH))

    result = ApprovalPolicy(dry_run=True, explicit_yes=True, allow_removals=True).evaluate(diff)

    assert result.approved is False


# --- Regra geral: nenhuma aprovação sem ApprovalResult aprovado -----------------------


def test_result_is_serializable_and_readable():
    diff = _diff_with(_entry(DiffChangeType.ADDED, DiffRiskLevel.LOW))

    result = ApprovalPolicy(explicit_yes=True).evaluate(diff)

    assert isinstance(result.approved, bool)
    assert isinstance(result.reason, str)
    assert len(result.reason) > 0
