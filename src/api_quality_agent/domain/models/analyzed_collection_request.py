from dataclasses import dataclass

from api_quality_agent.domain.models.endpoint_analysis import EndpointAnalysis
from api_quality_agent.domain.models.postman_collection_items import CollectionRequest


@dataclass(frozen=True)
class AnalyzedCollectionRequest:
    raw_request: CollectionRequest
    analysis: EndpointAnalysis
