import dataclasses

import pytest

from api_quality_agent.domain.exceptions import InputError
from api_quality_agent.domain.models import (
    DeclaredContractCatalog,
    DeclaredEndpointContract,
    DeclaredParameter,
    DeclaredRequestContract,
    DeclaredResponseContract,
    DeclaredSchema,
    ParameterLocation,
)

# --- DeclaredSchema ----------------------------------------------------------------


def test_declared_schema_scalar_is_valid():
    schema = DeclaredSchema(type="string", required=True, name="id")
    assert schema.type == "string"
    assert schema.required is True
    assert schema.properties == ()
    assert schema.items is None


def test_declared_schema_object_with_properties():
    child = DeclaredSchema(type="string", required=True, name="id")
    parent = DeclaredSchema(type="object", required=True, name="dado", properties=(child,))
    assert parent.properties == (child,)


def test_declared_schema_array_with_items():
    item = DeclaredSchema(type="object", required=True, properties=(DeclaredSchema(type="number", required=True, name="idObjetoTema"),))
    array = DeclaredSchema(type="array", required=True, name="lsObjetoTema", items=item)
    assert array.items is item


def test_declared_schema_rejects_unknown_type():
    with pytest.raises(InputError):
        DeclaredSchema(type="unknown", required=True)


def test_declared_schema_rejects_properties_on_non_object():
    child = DeclaredSchema(type="string", required=True, name="x")
    with pytest.raises(InputError):
        DeclaredSchema(type="string", required=True, properties=(child,))


def test_declared_schema_rejects_items_on_non_array():
    item = DeclaredSchema(type="string", required=True)
    with pytest.raises(InputError):
        DeclaredSchema(type="object", required=True, items=item)


def test_declared_schema_rejects_empty_name_when_provided():
    with pytest.raises(InputError):
        DeclaredSchema(type="string", required=True, name="   ")


def test_declared_schema_is_frozen():
    schema = DeclaredSchema(type="string", required=True, name="id")
    with pytest.raises(dataclasses.FrozenInstanceError):
        schema.type = "number"  # type: ignore[misc]


# --- DeclaredParameter ----------------------------------------------------------------


def test_declared_parameter_valid():
    parameter = DeclaredParameter(
        name="origem",
        location=ParameterLocation.PATH,
        required=True,
        schema=DeclaredSchema(type="string", required=True),
    )
    assert parameter.name == "origem"
    assert parameter.location is ParameterLocation.PATH


def test_declared_parameter_rejects_empty_name():
    with pytest.raises(InputError):
        DeclaredParameter(
            name="",
            location=ParameterLocation.HEADER,
            required=True,
            schema=DeclaredSchema(type="string", required=True),
        )


def test_declared_parameter_is_frozen():
    parameter = DeclaredParameter(
        name="origem",
        location=ParameterLocation.PATH,
        required=True,
        schema=DeclaredSchema(type="string", required=True),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        parameter.required = False  # type: ignore[misc]


# --- DeclaredRequestContract / DeclaredResponseContract ----------------------------------------------------------------


def test_declared_request_contract_defaults_are_empty():
    request = DeclaredRequestContract()
    assert request.headers == ()
    assert request.path_parameters == ()
    assert request.query_parameters == ()
    assert request.body_schema is None


def test_declared_request_contract_with_sections():
    header = DeclaredParameter(
        name="nmIdTransacaoExterno",
        location=ParameterLocation.HEADER,
        required=True,
        schema=DeclaredSchema(type="string", required=True),
    )
    body = DeclaredSchema(type="object", required=True, properties=(DeclaredSchema(type="number", required=False, name="nrOferta"),))
    request = DeclaredRequestContract(headers=(header,), body_schema=body)
    assert request.headers == (header,)
    assert request.body_schema is body


def test_declared_response_contract_holds_only_success_schema():
    schema = DeclaredSchema(type="object", required=True)
    response = DeclaredResponseContract(schema=schema)
    assert response.schema is schema


def test_declared_response_contract_can_be_empty():
    response = DeclaredResponseContract()
    assert response.schema is None


# --- DeclaredEndpointContract / DeclaredContractCatalog ----------------------------------------------------------------


def _endpoint_contract(**overrides) -> DeclaredEndpointContract:
    defaults = dict(
        method="POST",
        path="/teste/v{version}/cotacao/{origem}",
        request=DeclaredRequestContract(),
        response=DeclaredResponseContract(),
        source_sheet="Planilha1",
    )
    defaults.update(overrides)
    return DeclaredEndpointContract(**defaults)


def test_declared_endpoint_contract_valid():
    endpoint = _endpoint_contract()
    assert endpoint.method == "POST"
    assert endpoint.warnings == ()


def test_declared_endpoint_contract_rejects_empty_method():
    with pytest.raises(InputError):
        _endpoint_contract(method="")


def test_declared_endpoint_contract_rejects_empty_path():
    with pytest.raises(InputError):
        _endpoint_contract(path="")


def test_declared_endpoint_contract_rejects_empty_source_sheet():
    with pytest.raises(InputError):
        _endpoint_contract(source_sheet="")


def test_declared_endpoint_contract_is_frozen():
    endpoint = _endpoint_contract()
    with pytest.raises(dataclasses.FrozenInstanceError):
        endpoint.method = "GET"  # type: ignore[misc]


def test_declared_contract_catalog_valid():
    endpoint = _endpoint_contract()
    catalog = DeclaredContractCatalog(source_file="contrato.xlsx", contracts=(endpoint,))
    assert catalog.source_file == "contrato.xlsx"
    assert catalog.contracts == (endpoint,)


def test_declared_contract_catalog_defaults_to_no_contracts():
    catalog = DeclaredContractCatalog(source_file="contrato.xlsx")
    assert catalog.contracts == ()


def test_declared_contract_catalog_rejects_empty_source_file():
    with pytest.raises(InputError):
        DeclaredContractCatalog(source_file="")


def test_declared_contract_catalog_is_frozen():
    catalog = DeclaredContractCatalog(source_file="contrato.xlsx")
    with pytest.raises(dataclasses.FrozenInstanceError):
        catalog.source_file = "outro.xlsx"  # type: ignore[misc]
