from enum import Enum


class AuthType(str, Enum):
    NONE = "none"
    INHERIT = "inherit"
    BEARER = "bearer"
    API_KEY = "apikey"
    BASIC = "basic"
    OAUTH2 = "oauth2"
    DIGEST = "digest"
    AWS_V4 = "awsv4"
    HAWK = "hawk"
    NTLM = "ntlm"
    EDGEGRID = "edgegrid"
    UNKNOWN = "unknown"
