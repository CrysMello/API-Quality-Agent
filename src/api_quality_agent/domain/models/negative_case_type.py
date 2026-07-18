from enum import Enum


class NegativeCaseType(str, Enum):
    MISSING_REQUIRED_FIELD = "missing_required_field"
    INVALID_ENUM_VALUE = "invalid_enum_value"
    INVALID_TYPE = "invalid_type"
    LIMIT_VIOLATION = "limit_violation"
