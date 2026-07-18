from enum import Enum


class AssertionOrigin(str, Enum):
    CONTRACT = "contract"
    EXAMPLE = "example"
    CONFIGURATION = "configuration"
    CONTEXT = "context"
