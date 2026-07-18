from enum import Enum


class DiffCategory(str, Enum):
    SCRIPT = "script"
    MANAGED_BLOCK = "managed_block"
    VARIABLE = "variable"
    REQUEST = "request"
