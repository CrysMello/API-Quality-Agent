from dataclasses import dataclass


@dataclass(frozen=True)
class ContractValidationIssue:
    severity: str  # "error" | "warning"
    sheet: str
    section: str | None
    row_number: int | None
    field: str | None
    message: str
