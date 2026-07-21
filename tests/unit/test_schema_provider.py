from api_quality_agent.domain.services import ExcelSchemaProvider, InferenceSchemaProvider, SchemaInferenceEngine
from api_quality_agent.domain.services.canonical_endpoint_normalizer import CanonicalEndpointNormalizer
from api_quality_agent.domain.services.contract_endpoint_matcher import ContractEndpointMatcher
from api_quality_agent.domain.models import DeclaredContractCatalog
from api_quality_agent.ports.outbound import SchemaProvider


def test_excel_schema_provider_satisfies_the_schema_provider_protocol():
    provider = ExcelSchemaProvider(
        catalog=DeclaredContractCatalog(source_file="c.xlsx"),
        matcher=ContractEndpointMatcher(CanonicalEndpointNormalizer()),
        normalizer=CanonicalEndpointNormalizer(),
    )
    assert isinstance(provider, SchemaProvider)


def test_inference_schema_provider_satisfies_the_schema_provider_protocol():
    provider = InferenceSchemaProvider(SchemaInferenceEngine())
    assert isinstance(provider, SchemaProvider)
