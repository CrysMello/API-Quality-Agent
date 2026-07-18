import pytest

from api_quality_agent.cli.exit_codes import (
    AMBIGUOUS_SELECTION,
    AUTHENTICATION_FAILURE,
    FUNCTIONAL_FAILURE,
    INTEGRATION_FAILURE,
    INTERNAL_FAILURE,
    INVALID_INPUT_OR_CONFIGURATION,
    RESOURCE_NOT_FOUND,
    UPDATE_NOT_APPROVED,
    resolve_exit_code,
)
from api_quality_agent.domain.exceptions import (
    AmbiguousResourceError,
    ApiQualityAgentError,
    AuthenticationError,
    ConfigurationError,
    InputError,
    IntegrationError,
    ResourceNotFoundError,
    SelectionError,
    UpdateNotApprovedError,
)


@pytest.mark.parametrize(
    ("exception", "expected_code"),
    [
        (AuthenticationError("falha de autenticação"), AUTHENTICATION_FAILURE),
        (AmbiguousResourceError("ambíguo"), AMBIGUOUS_SELECTION),
        (ResourceNotFoundError("não encontrado"), RESOURCE_NOT_FOUND),
        (UpdateNotApprovedError("não aprovado"), UPDATE_NOT_APPROVED),
        (IntegrationError("falha de integração"), INTEGRATION_FAILURE),
        (ConfigurationError("config inválida"), INVALID_INPUT_OR_CONFIGURATION),
        (InputError("entrada inválida"), INVALID_INPUT_OR_CONFIGURATION),
        (SelectionError("seleção inválida"), INVALID_INPUT_OR_CONFIGURATION),
        (ApiQualityAgentError("erro genérico do domínio"), FUNCTIONAL_FAILURE),
        (RuntimeError("bug inesperado"), INTERNAL_FAILURE),
    ],
)
def test_resolve_exit_code(exception, expected_code):
    assert resolve_exit_code(exception) == expected_code
