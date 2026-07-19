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

# Convenção de códigos de saída da CLI. Números já publicados nunca são
# reaproveitados para outro significado — novos cenários recebem um código
# novo (ver OPERATION_CANCELLED) em vez de renumerar os existentes.
SUCCESS = 0
FUNCTIONAL_FAILURE = 1
INVALID_INPUT_OR_CONFIGURATION = 2
AUTHENTICATION_FAILURE = 3
RESOURCE_NOT_FOUND = 4
AMBIGUOUS_SELECTION = 5
INTEGRATION_FAILURE = 6
UPDATE_NOT_APPROVED = 7
INTERNAL_FAILURE = 8
OPERATION_CANCELLED = 9

# Ordem importa: subclasses mais específicas devem ser checadas antes de suas
# bases (ex.: AuthenticationError antes de IntegrationError).
_EXCEPTION_EXIT_CODES: tuple[tuple[type[BaseException], int], ...] = (
    (AuthenticationError, AUTHENTICATION_FAILURE),
    (AmbiguousResourceError, AMBIGUOUS_SELECTION),
    (ResourceNotFoundError, RESOURCE_NOT_FOUND),
    (UpdateNotApprovedError, UPDATE_NOT_APPROVED),
    (IntegrationError, INTEGRATION_FAILURE),
    (ConfigurationError, INVALID_INPUT_OR_CONFIGURATION),
    (InputError, INVALID_INPUT_OR_CONFIGURATION),
    (SelectionError, INVALID_INPUT_OR_CONFIGURATION),
    (ApiQualityAgentError, FUNCTIONAL_FAILURE),
)


def resolve_exit_code(exc: BaseException) -> int:
    for exception_type, exit_code in _EXCEPTION_EXIT_CODES:
        if isinstance(exc, exception_type):
            return exit_code
    return INTERNAL_FAILURE
