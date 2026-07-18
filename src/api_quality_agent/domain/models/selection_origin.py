from enum import Enum


class SelectionOrigin(str, Enum):
    ACTIVE = "active"
    TEMPORARY = "temporary"
