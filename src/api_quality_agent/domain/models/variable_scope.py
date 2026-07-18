from enum import Enum


class VariableScope(str, Enum):
    COLLECTION = "collection"
    ENVIRONMENT = "environment"
    LOCAL = "local"
