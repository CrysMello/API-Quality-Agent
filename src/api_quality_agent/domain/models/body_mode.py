from enum import Enum


class BodyMode(str, Enum):
    NONE = "none"
    RAW = "raw"
    FORMDATA = "formdata"
    URLENCODED = "urlencoded"
    GRAPHQL = "graphql"
    FILE = "file"
    UNKNOWN = "unknown"
