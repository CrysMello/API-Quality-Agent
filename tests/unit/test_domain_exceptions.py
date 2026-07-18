import pytest

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
    "exception_type",
    [
        ConfigurationError,
        InputError,
        SelectionError,
        IntegrationError,
        AuthenticationError,
        ResourceNotFoundError,
        AmbiguousResourceError,
        UpdateNotApprovedError,
    ],
)
def test_all_errors_inherit_from_base(exception_type):
    assert issubclass(exception_type, ApiQualityAgentError)


def test_base_error_is_exception():
    assert issubclass(ApiQualityAgentError, Exception)


def test_authentication_error_is_integration_error():
    assert issubclass(AuthenticationError, IntegrationError)


@pytest.mark.parametrize("exception_type", [ResourceNotFoundError, AmbiguousResourceError])
def test_selection_related_errors_inherit_from_selection_error(exception_type):
    assert issubclass(exception_type, SelectionError)


def test_errors_carry_message():
    error = ConfigurationError("mensagem de teste")
    assert str(error) == "mensagem de teste"
