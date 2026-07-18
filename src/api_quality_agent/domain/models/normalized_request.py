from dataclasses import dataclass

from api_quality_agent.domain.models.normalization_warning import NormalizationWarning
from api_quality_agent.domain.models.normalized_auth import NormalizedAuth
from api_quality_agent.domain.models.normalized_body import NormalizedBody
from api_quality_agent.domain.models.normalized_header import NormalizedHeader
from api_quality_agent.domain.models.normalized_url import NormalizedUrl


@dataclass(frozen=True)
class NormalizedRequest:
    request_id: str | None
    name: str | None
    method: str | None
    url: NormalizedUrl
    auth: NormalizedAuth
    body: NormalizedBody
    headers: tuple[NormalizedHeader, ...]
    warnings: tuple[NormalizationWarning, ...]
