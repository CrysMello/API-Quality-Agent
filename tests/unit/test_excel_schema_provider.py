from api_quality_agent.domain.models import (
    CollectionRequest,
    DeclaredContractCatalog,
    DeclaredEndpointContract,
    DeclaredRequestContract,
    DeclaredResponseContract,
    DeclaredSchema,
)
from api_quality_agent.domain.services import ExcelSchemaProvider
from api_quality_agent.domain.services.canonical_endpoint_normalizer import CanonicalEndpointNormalizer
from api_quality_agent.domain.services.contract_endpoint_matcher import ContractEndpointMatcher


def _request(method, url):
    return CollectionRequest(
        item_id=None,
        name="Request",
        description=None,
        method=method,
        url=url,
        url_raw=url if isinstance(url, str) else None,
        headers=(),
        body=None,
        auth=None,
        events=(),
        examples=(),
    )


def _contract(method, path, response_schema=None, source_sheet="Planilha1"):
    return DeclaredEndpointContract(
        method=method,
        path=path,
        request=DeclaredRequestContract(),
        response=DeclaredResponseContract(schema=response_schema),
        source_sheet=source_sheet,
    )


def _provider(catalog):
    normalizer = CanonicalEndpointNormalizer()
    return ExcelSchemaProvider(
        catalog=catalog, matcher=ContractEndpointMatcher(normalizer), normalizer=normalizer
    )


def test_resolves_schema_for_matched_endpoint():
    response_schema = DeclaredSchema(
        type="object",
        required=True,
        properties=(
            DeclaredSchema(type="string", required=True, name="id"),
            DeclaredSchema(type="string", required=False, name="tipo"),
        ),
    )
    catalog = DeclaredContractCatalog(
        source_file="c.xlsx", contracts=(_contract("GET", "/v2/pet/{petId}", response_schema),)
    )
    request = _request("GET", {"path": ["v2", "pet", "{{petId}}"]})

    resolution = _provider(catalog).resolve(request)

    assert resolution.schema == {
        "type": "object",
        "properties": {"id": {"type": "string"}, "tipo": {"type": "string"}},
        "required": ["id"],
    }
    assert resolution.warnings == ()


def test_nested_array_schema_is_converted_correctly():
    item_schema = DeclaredSchema(
        type="object", required=True, properties=(DeclaredSchema(type="number", required=True, name="idItem"),)
    )
    response_schema = DeclaredSchema(
        type="object",
        required=True,
        properties=(DeclaredSchema(type="array", required=True, name="itens", items=item_schema),),
    )
    catalog = DeclaredContractCatalog(
        source_file="c.xlsx", contracts=(_contract("GET", "/v2/itens", response_schema),)
    )
    request = _request("GET", "/v2/itens")

    resolution = _provider(catalog).resolve(request)

    assert resolution.schema == {
        "type": "object",
        "properties": {
            "itens": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"idItem": {"type": "number"}},
                    "required": ["idItem"],
                },
            }
        },
        "required": ["itens"],
    }


def test_not_found_returns_none_schema():
    catalog = DeclaredContractCatalog(source_file="c.xlsx", contracts=(_contract("GET", "/v2/pet"),))
    request = _request("POST", "/v2/pet")

    resolution = _provider(catalog).resolve(request)

    assert resolution.schema is None


def test_ambiguous_returns_none_schema():
    contract_a = _contract("GET", "/v2/pet/{id}", source_sheet="Planilha1")
    contract_b = _contract("GET", "/v2/pet/{petId}", source_sheet="Planilha2")
    catalog = DeclaredContractCatalog(source_file="c.xlsx", contracts=(contract_a, contract_b))
    request = _request("GET", "/v2/pet/:x")

    resolution = _provider(catalog).resolve(request)

    assert resolution.schema is None


def test_matched_endpoint_without_declared_schema_returns_none():
    catalog = DeclaredContractCatalog(
        source_file="c.xlsx", contracts=(_contract("GET", "/v2/pet", response_schema=None),)
    )
    request = _request("GET", "/v2/pet")

    resolution = _provider(catalog).resolve(request)

    assert resolution.schema is None


def test_invalid_url_never_raises_just_returns_none():
    catalog = DeclaredContractCatalog(source_file="c.xlsx", contracts=(_contract("GET", "/v2/pet"),))
    request = _request("GET", None)

    resolution = _provider(catalog).resolve(request)

    assert resolution.schema is None


def test_never_accesses_excel_file_directly():
    # Garantia de escopo: o provider só depende do catálogo já construído,
    # do matcher e do normalizador — nenhuma dependência de leitura de arquivo.
    import inspect

    signature = inspect.signature(ExcelSchemaProvider.__init__)
    assert list(signature.parameters) == ["self", "catalog", "matcher", "normalizer"]
