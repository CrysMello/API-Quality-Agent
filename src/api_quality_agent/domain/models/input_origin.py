from enum import Enum


class InputOrigin(str, Enum):
    FILE = "file"
    STDIN = "stdin"
    INLINE = "inline"
