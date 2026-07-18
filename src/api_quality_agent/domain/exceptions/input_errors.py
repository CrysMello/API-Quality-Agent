from api_quality_agent.domain.exceptions.errors import InputError


class InputFileNotFoundError(InputError):
    pass


class UnsupportedInputExtensionError(InputError):
    pass


class EmptyInputError(InputError):
    pass


class InputSizeLimitExceededError(InputError):
    pass


class InputEncodingError(InputError):
    pass


class InvalidJsonError(InputError):
    pass
