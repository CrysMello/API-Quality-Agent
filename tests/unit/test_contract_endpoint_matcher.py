import inspect

from api_quality_agent.domain.models import (
    DeclaredContractCatalog,
    DeclaredEndpointContract,
    DeclaredRequestContract,
    DeclaredResponseContract,
    MatchStatus,
)
from api_quality_agent.domain.services import CanonicalEndpointNormalizer, ContractEndpointMatcher


def _contract(method: str, path: str, source_sheet: str = "Planilha1") -> DeclaredEndpointContract:
    return DeclaredEndpointContract(
        method=method,
        path=path,
        request=DeclaredRequestContract(),
        response=DeclaredResponseContract(),
        source_sheet=source_sheet,
    )


def _matcher() -> ContractEndpointMatcher:
    return ContractEndpointMatcher(CanonicalEndpointNormalizer())


def test_matches_when_method_and_canonical_path_are_equal():
    catalog = DeclaredContractCatalog(
        source_file="c.xlsx", contracts=(_contract("GET", "/v2/pet/{petId}"),)
    )
    endpoint = CanonicalEndpointNormalizer().normalize_collection_request(
        "GET", {"path": ["v2", "pet", "{{petId}}"]}
    )

    result = _matcher().match(endpoint, catalog)

    assert result.status == MatchStatus.MATCHED
    assert result.contract is catalog.contracts[0]


def test_parameter_names_do_not_need_to_match():
    catalog = DeclaredContractCatalog(source_file="c.xlsx", contracts=(_contract("GET", "/v2/pet/{id}"),))
    endpoint = CanonicalEndpointNormalizer().normalize_collection_request("GET", "/v2/pet/:petId")

    result = _matcher().match(endpoint, catalog)

    assert result.status == MatchStatus.MATCHED


def test_no_match_returns_not_found():
    catalog = DeclaredContractCatalog(source_file="c.xlsx", contracts=(_contract("GET", "/v2/pet"),))
    endpoint = CanonicalEndpointNormalizer().normalize_collection_request("POST", "/v2/pet")

    result = _matcher().match(endpoint, catalog)

    assert result.status == MatchStatus.NOT_FOUND
    assert result.contract is None


def test_same_path_different_method_are_not_confused():
    catalog = DeclaredContractCatalog(
        source_file="c.xlsx",
        contracts=(_contract("POST", "/v2/pet"), _contract("PUT", "/v2/pet")),
    )
    endpoint = CanonicalEndpointNormalizer().normalize_collection_request("PUT", "/v2/pet")

    result = _matcher().match(endpoint, catalog)

    assert result.status == MatchStatus.MATCHED
    assert result.contract is not None
    assert result.contract.method == "PUT"


def test_duplicate_endpoint_in_catalog_is_ambiguous_and_never_auto_chosen():
    contract_a = _contract("GET", "/v2/pet/{id}", source_sheet="Planilha1")
    contract_b = _contract("GET", "/v2/pet/{petId}", source_sheet="Planilha2")
    catalog = DeclaredContractCatalog(source_file="c.xlsx", contracts=(contract_a, contract_b))
    endpoint = CanonicalEndpointNormalizer().normalize_collection_request("GET", "/v2/pet/:x")

    result = _matcher().match(endpoint, catalog)

    assert result.status == MatchStatus.AMBIGUOUS
    assert result.contract is None
    assert len(result.candidates) == 2
    assert contract_a in result.candidates
    assert contract_b in result.candidates


def test_match_all_matches_every_endpoint_independently():
    catalog = DeclaredContractCatalog(
        source_file="c.xlsx",
        contracts=(_contract("GET", "/v2/pet"), _contract("POST", "/v2/pet")),
    )
    normalizer = CanonicalEndpointNormalizer()
    endpoints = (
        normalizer.normalize_collection_request("GET", "/v2/pet"),
        normalizer.normalize_collection_request("POST", "/v2/pet"),
        normalizer.normalize_collection_request("DELETE", "/v2/pet"),
    )

    results = _matcher().match_all(endpoints, catalog)

    assert [result.status for result in results] == [
        MatchStatus.MATCHED,
        MatchStatus.MATCHED,
        MatchStatus.NOT_FOUND,
    ]


def test_matcher_only_depends_on_the_normalizer():
    # Garantia de escopo: nenhuma dependência de Excel/Collection real —
    # só o CanonicalEndpointNormalizer.
    signature = inspect.signature(ContractEndpointMatcher.__init__)
    assert list(signature.parameters) == ["self", "normalizer"]
