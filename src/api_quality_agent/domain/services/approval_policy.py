from dataclasses import dataclass

from api_quality_agent.domain.models import ApprovalResult, DiffResult


@dataclass(frozen=True)
class ApprovalPolicy:
    dry_run: bool = False
    explicit_yes: bool = False
    allow_removals: bool = False

    def evaluate(self, diff: DiffResult) -> ApprovalResult:
        if not diff.has_changes:
            return ApprovalResult(
                approved=True, reason="Nenhuma alteração detectada; não há o que aprovar."
            )

        # Regra absoluta: dry-run nunca aprova escrita, mesmo com aprovação explícita.
        if self.dry_run:
            return ApprovalResult(
                approved=False,
                reason="Execução em modo dry-run: a escrita é sempre impedida.",
            )

        if diff.has_removals and not self.allow_removals:
            return ApprovalResult(
                approved=False,
                reason=(
                    "Remoções detectadas sem autorização explícita para removê-las; "
                    "atualização bloqueada."
                ),
            )

        if not self.explicit_yes:
            return ApprovalResult(
                approved=False,
                reason="Nenhuma aprovação explícita foi fornecida (flag --yes ausente).",
            )

        return ApprovalResult(approved=True, reason="Atualização aprovada explicitamente.")
