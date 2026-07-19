from api_quality_agent.domain.exceptions.errors import ApiQualityAgentError, InputError


class InvalidExecutionResultError(InputError):
    pass


class UnsupportedExecutionResultSchemaError(InputError):
    pass


class ReportAlreadyExistsError(ApiQualityAgentError):
    pass
