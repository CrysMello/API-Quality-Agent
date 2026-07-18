from api_quality_agent.domain.exceptions.errors import InputError


class InvalidApiSpecificationError(InputError):
    pass


class UnsupportedSpecificationVersionError(InputError):
    pass


class UnresolvedReferenceError(InputError):
    pass
