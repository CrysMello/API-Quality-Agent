from enum import Enum


class ParameterLocation(str, Enum):
    PATH = "path"
    QUERY = "query"
    HEADER = "header"
    COOKIE = "cookie"
    FORM_DATA = "formData"
