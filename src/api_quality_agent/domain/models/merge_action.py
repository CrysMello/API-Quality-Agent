from enum import Enum


class MergeAction(str, Enum):
    INSERTED = "inserted"
    REPLACED = "replaced"
