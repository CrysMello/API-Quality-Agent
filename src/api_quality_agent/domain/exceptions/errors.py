class ApiQualityAgentError(Exception):
    pass


class ConfigurationError(ApiQualityAgentError):
    pass


class InputError(ApiQualityAgentError):
    pass


class SelectionError(ApiQualityAgentError):
    pass


class IntegrationError(ApiQualityAgentError):
    pass


class AuthenticationError(IntegrationError):
    pass


class ResourceNotFoundError(SelectionError):
    pass


class AmbiguousResourceError(SelectionError):
    pass


class UpdateNotApprovedError(ApiQualityAgentError):
    pass
