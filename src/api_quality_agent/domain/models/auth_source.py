from enum import Enum


class AuthSource(str, Enum):
    REQUEST = "request"
    FOLDER = "folder"
    COLLECTION = "collection"
    INHERITED = "inherited"
    NONE = "none"
