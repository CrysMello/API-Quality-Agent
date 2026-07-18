from enum import Enum


class AssertionType(str, Enum):
    STATUS_CODE = "status_code"
    CONTENT_TYPE = "content_type"
    RESPONSE_TIME = "response_time"
    VALID_JSON_BODY = "valid_json_body"
    SCHEMA = "schema"
    ARRAY_NOT_EMPTY = "array_not_empty"
    NO_EXTRA_PROPERTIES = "no_extra_properties"
    REQUIRED_FIELD_PRESENT = "required_field_present"
    SNAPSHOT = "snapshot"
