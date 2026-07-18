from enum import Enum


class ContractChangeType(str, Enum):
    FIELD_ADDED = "field_added"
    FIELD_REMOVED = "field_removed"
    TYPE_CHANGED = "type_changed"
    REQUIRED_CHANGED = "required_changed"
    ENUM_CHANGED = "enum_changed"
    STATUS_CODE_CHANGED = "status_code_changed"
    CONTENT_TYPE_CHANGED = "content_type_changed"
