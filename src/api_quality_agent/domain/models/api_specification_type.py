from enum import Enum


class ApiSpecificationType(str, Enum):
    OPENAPI = "openapi"
    SWAGGER = "swagger"
