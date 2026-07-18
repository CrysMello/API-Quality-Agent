from enum import Enum


class InfrastructureFailureType(str, Enum):
    EXECUTABLE_NOT_FOUND = "executable_not_found"
    TIMEOUT = "timeout"
    INVALID_COLLECTION = "invalid_collection"
    UNEXPECTED_ERROR = "unexpected_error"
