from api_quality_agent.domain.exceptions.errors import InputError


class DuplicateManagedBlockError(InputError):
    pass


class UnclosedManagedBlockError(InputError):
    pass


class CorruptedManagedBlockError(InputError):
    pass
