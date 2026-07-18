from dataclasses import dataclass
from datetime import datetime
from typing import Any

from api_quality_agent.domain.models.snapshot_key import SnapshotKey


@dataclass(frozen=True)
class ContractSnapshot:
    # Representação puramente estrutural do contrato de um endpoint — nunca
    # valores reais de resposta. `schema` é um JSON Schema (tipos/obrigato-
    # riedade/enum), nunca um exemplo de payload.
    key: SnapshotKey
    captured_at: datetime
    status_codes: tuple[str, ...]
    content_types: tuple[str, ...]
    schema: dict[str, Any] | None
