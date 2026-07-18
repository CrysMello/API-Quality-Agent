import typing

from api_quality_agent.domain.models import (
    AuthSource,
    AuthType,
    BodyMode,
    CollectionRequest,
    NormalizationContext,
    NormalizedAuth,
    NormalizedBody,
    NormalizedRequest,
    NormalizedUrl,
)
from api_quality_agent.domain.services import PostmanRequestNormalizer


def _build_request(
    *,
    item_id="req-1",
    name="Request",
    method="GET",
    url=None,
    headers=(),
    body=None,
    auth=None,
) -> CollectionRequest:
    return CollectionRequest(
        item_id=item_id,
        name=name,
        description=None,
        method=method,
        url=url,
        url_raw=None,
        headers=headers,
        body=body,
        auth=auth,
        events=(),
        examples=(),
    )


# --- URL ---------------------------------------------------------------------


def test_url_as_string_is_normalized():
    request = _build_request(url="https://api.exemplo.com/v1/pets?limit=10")

    result = PostmanRequestNormalizer().normalize(request).url

    assert result.raw == "https://api.exemplo.com/v1/pets?limit=10"
    assert result.protocol == "https"
    assert result.host == ("api", "exemplo", "com")
    assert result.path == ("v1", "pets")
    assert result.query_parameters[0].key == "limit"
    assert result.query_parameters[0].value == "10"


def test_url_as_object_is_normalized():
    request = _build_request(
        url={
            "raw": "https://api.exemplo.com/v1/pets",
            "protocol": "https",
            "host": ["api", "exemplo", "com"],
            "path": ["v1", "pets"],
        }
    )

    result = PostmanRequestNormalizer().normalize(request).url

    assert result.protocol == "https"
    assert result.host == ("api", "exemplo", "com")
    assert result.path == ("v1", "pets")


def test_string_and_object_url_produce_equivalent_normalized_result():
    string_request = _build_request(url="https://api.exemplo.com/v1/pets?limit=10")
    object_request = _build_request(
        url={
            "raw": "https://api.exemplo.com/v1/pets?limit=10",
            "protocol": "https",
            "host": ["api", "exemplo", "com"],
            "path": ["v1", "pets"],
            "query": [{"key": "limit", "value": "10"}],
        }
    )
    normalizer = PostmanRequestNormalizer()

    from_string = normalizer.normalize(string_request).url
    from_object = normalizer.normalize(object_request).url

    assert from_string.protocol == from_object.protocol
    assert from_string.host == from_object.host
    assert from_string.path == from_object.path
    assert from_string.query_parameters == from_object.query_parameters


def test_url_query_parameters_are_extracted():
    request = _build_request(
        url={"raw": "https://x/y", "query": [{"key": "a", "value": "1"}, {"key": "b", "value": "2"}]}
    )

    result = PostmanRequestNormalizer().normalize(request).url

    assert len(result.query_parameters) == 2
    assert result.query_parameters[0].key == "a"
    assert result.query_parameters[1].key == "b"


def test_url_disabled_query_parameter_is_identifiable():
    request = _build_request(
        url={"raw": "https://x/y", "query": [{"key": "debug", "value": "true", "disabled": True}]}
    )

    result = PostmanRequestNormalizer().normalize(request).url

    assert result.query_parameters[0].disabled is True


def test_url_variables_are_extracted():
    request = _build_request(
        url={"raw": "https://x/{{id}}", "variable": [{"key": "id", "value": "123"}]}
    )

    result = PostmanRequestNormalizer().normalize(request).url

    assert len(result.variables) == 1
    assert result.variables[0].key == "id"
    assert result.variables[0].value == "123"


def test_incomplete_url_does_not_invent_missing_fields():
    request = _build_request(url={"host": ["api", "exemplo", "com"]})

    result = PostmanRequestNormalizer().normalize(request).url

    assert result.raw is None
    assert result.path == ()
    assert result.protocol is None


def test_unsupported_url_shape_generates_warning_without_crashing():
    request = _build_request(url=12345)  # type: ignore[arg-type]

    normalized = PostmanRequestNormalizer().normalize(request)

    assert normalized.url == NormalizedUrl(
        raw=None, protocol=None, host=(), path=(), query_parameters=(), variables=()
    )
    assert any(w.code == "UNSUPPORTED_URL_SHAPE" for w in normalized.warnings)


def test_normalizing_url_does_not_modify_original_request_object():
    original_url = {"raw": "https://x/y", "host": ["x"], "path": ["y"]}
    request = _build_request(url=original_url)

    PostmanRequestNormalizer().normalize(request)

    assert request.url == original_url


# --- Auth ----------------------------------------------------------------------


def test_auth_explicitly_none():
    request = _build_request(auth={"type": "noauth"})

    result = PostmanRequestNormalizer().normalize(request).auth

    assert result.auth_type == AuthType.NONE
    assert result.source == AuthSource.NONE


def test_auth_missing_is_treated_as_inherited():
    request = _build_request(auth=None)

    result = PostmanRequestNormalizer().normalize(request).auth

    assert result.auth_type == AuthType.INHERIT
    assert result.source == AuthSource.INHERITED


def test_auth_missing_with_known_absent_parent_is_none():
    request = _build_request(auth=None)
    context = NormalizationContext(parent_has_explicit_auth=False)

    result = PostmanRequestNormalizer().normalize(request, context).auth

    assert result.auth_type == AuthType.NONE
    assert result.source == AuthSource.NONE


def test_auth_missing_without_context_generates_unresolved_warning():
    request = _build_request(auth=None)

    normalized = PostmanRequestNormalizer().normalize(request)

    assert any(w.code == "AUTH_SOURCE_UNRESOLVED" for w in normalized.warnings)


def test_auth_bearer_with_variable_reference():
    request = _build_request(
        auth={"type": "bearer", "bearer": [{"key": "token", "value": "{{token}}", "type": "string"}]}
    )

    result = PostmanRequestNormalizer().normalize(request).auth

    assert result.auth_type == AuthType.BEARER
    assert result.variable_references == ("token",)
    assert result.has_sensitive_values is False


def test_auth_bearer_with_literal_sensitive_value():
    request = _build_request(
        auth={
            "type": "bearer",
            "bearer": [{"key": "token", "value": "super-secret-literal", "type": "string"}],
        }
    )

    result = PostmanRequestNormalizer().normalize(request).auth

    assert result.auth_type == AuthType.BEARER
    assert result.has_sensitive_values is True
    assert "super-secret-literal" not in repr(result)


def test_auth_api_key():
    request = _build_request(
        auth={
            "type": "apikey",
            "apikey": [
                {"key": "key", "value": "X-API-Key", "type": "string"},
                {"key": "value", "value": "{{apiKeyValue}}", "type": "string"},
            ],
        }
    )

    result = PostmanRequestNormalizer().normalize(request).auth

    assert result.auth_type == AuthType.API_KEY
    assert "apiKeyValue" in result.variable_references


def test_auth_basic():
    request = _build_request(
        auth={
            "type": "basic",
            "basic": [
                {"key": "username", "value": "admin", "type": "string"},
                {"key": "password", "value": "hunter2", "type": "string"},
            ],
        }
    )

    result = PostmanRequestNormalizer().normalize(request).auth

    assert result.auth_type == AuthType.BASIC
    assert result.has_sensitive_values is True


def test_auth_oauth2_is_recognized_without_full_interpretation():
    request = _build_request(
        auth={"type": "oauth2", "oauth2": [{"key": "accessToken", "value": "abc", "type": "string"}]}
    )

    result = PostmanRequestNormalizer().normalize(request).auth

    assert result.auth_type == AuthType.OAUTH2
    assert result.raw_type == "oauth2"


def test_auth_unknown_type_becomes_unknown_and_does_not_fail_parsing():
    request = _build_request(auth={"type": "future-auth-scheme"})

    normalized = PostmanRequestNormalizer().normalize(request)

    assert normalized.auth.auth_type == AuthType.UNKNOWN
    assert normalized.auth.raw_type == "future-auth-scheme"
    assert any(w.code == "UNKNOWN_AUTH_TYPE" for w in normalized.warnings)


def test_secret_value_never_appears_in_normalization_warnings():
    request = _build_request(auth={"type": "future-auth-scheme", "future-auth-scheme": [{"value": "top-secret"}]})

    normalized = PostmanRequestNormalizer().normalize(request)

    for warning in normalized.warnings:
        assert "top-secret" not in warning.message


def test_normalizing_auth_does_not_modify_original_request_object():
    original_auth = {"type": "bearer", "bearer": [{"key": "token", "value": "abc"}]}
    request = _build_request(auth=original_auth)

    PostmanRequestNormalizer().normalize(request)

    assert request.auth == original_auth


# --- Body ------------------------------------------------------------------


def test_body_absent():
    request = _build_request(body=None)

    result = PostmanRequestNormalizer().normalize(request).body

    assert result.mode == BodyMode.NONE
    assert result.has_content is False


def test_body_raw_empty():
    request = _build_request(body={"mode": "raw", "raw": ""})

    result = PostmanRequestNormalizer().normalize(request).body

    assert result.mode == BodyMode.RAW
    assert result.has_content is False
    assert result.text_content == ""


def test_body_raw_json_with_content_type_header():
    request = _build_request(
        headers=({"key": "Content-Type", "value": "application/json"},),
        body={"mode": "raw", "raw": '{"name": "Rex"}', "options": {"raw": {"language": "json"}}},
    )

    result = PostmanRequestNormalizer().normalize(request).body

    assert result.mode == BodyMode.RAW
    assert result.content_type == "application/json"
    assert result.text_content == '{"name": "Rex"}'
    assert result.has_content is True


def test_body_raw_plain_text_without_content_type():
    request = _build_request(body={"mode": "raw", "raw": "texto simples"})

    result = PostmanRequestNormalizer().normalize(request).body

    assert result.content_type is None
    assert result.text_content == "texto simples"


def test_body_formdata():
    request = _build_request(
        body={"mode": "formdata", "formdata": [{"key": "file", "value": "x", "type": "text"}]}
    )

    result = PostmanRequestNormalizer().normalize(request).body

    assert result.mode == BodyMode.FORMDATA
    assert result.fields[0].key == "file"
    assert result.has_content is True


def test_body_urlencoded():
    request = _build_request(
        body={"mode": "urlencoded", "urlencoded": [{"key": "a", "value": "1"}]}
    )

    result = PostmanRequestNormalizer().normalize(request).body

    assert result.mode == BodyMode.URLENCODED
    assert result.fields[0].key == "a"
    assert result.fields[0].value == "1"


def test_body_graphql():
    request = _build_request(
        body={"mode": "graphql", "graphql": {"query": "{ pets { id } }", "variables": "{}"}}
    )

    result = PostmanRequestNormalizer().normalize(request).body

    assert result.mode == BodyMode.GRAPHQL
    assert result.graphql_query == "{ pets { id } }"
    assert result.has_content is True


def test_body_file_uses_metadata_only():
    request = _build_request(body={"mode": "file", "file": {"src": "/tmp/imagem.png"}})

    result = PostmanRequestNormalizer().normalize(request).body

    assert result.mode == BodyMode.FILE
    assert result.has_content is True
    assert result.fields[0].value == "/tmp/imagem.png"


def test_body_unknown_mode_generates_warning_without_losing_data():
    request = _build_request(body={"mode": "future-mode", "future-mode": {"x": 1}})

    normalized = PostmanRequestNormalizer().normalize(request)

    assert normalized.body.mode == BodyMode.UNKNOWN
    assert any(w.code == "UNKNOWN_BODY_MODE" for w in normalized.warnings)


def test_body_disabled_field_is_identifiable():
    request = _build_request(
        body={
            "mode": "urlencoded",
            "urlencoded": [{"key": "a", "value": "1", "disabled": True}],
        }
    )

    result = PostmanRequestNormalizer().normalize(request).body

    assert result.fields[0].disabled is True


def test_body_variable_reference_is_extracted():
    request = _build_request(body={"mode": "raw", "raw": '{"token": "{{token}}"}'})

    result = PostmanRequestNormalizer().normalize(request).body

    assert result.variable_references == ("token",)


def test_normalizing_body_does_not_modify_original_request_object():
    original_body = {"mode": "raw", "raw": '{"a": 1}'}
    request = _build_request(body=original_body)

    PostmanRequestNormalizer().normalize(request)

    assert request.body == original_body


# --- Arquitetura / comportamento geral -----------------------------------------


def test_normalized_request_exposes_only_typed_normalized_fields():
    hints = typing.get_type_hints(NormalizedRequest)

    assert hints["url"] is NormalizedUrl
    assert hints["auth"] is NormalizedAuth
    assert hints["body"] is NormalizedBody


def test_raw_collection_request_remains_available_after_normalization():
    raw_auth = {"type": "bearer", "bearer": [{"key": "token", "value": "{{t}}"}]}
    request = _build_request(url="https://x/y", auth=raw_auth)

    PostmanRequestNormalizer().normalize(request)

    assert request.auth == raw_auth
    assert request.url == "https://x/y"


def test_normalization_is_deterministic_and_idempotent():
    request = _build_request(
        method="POST", url="https://x/y", body={"mode": "raw", "raw": "{}"}
    )
    normalizer = PostmanRequestNormalizer()

    first = normalizer.normalize(request)
    second = normalizer.normalize(request)

    assert first == second


def test_secret_never_appears_in_repr_or_str_of_normalized_request():
    request = _build_request(
        auth={
            "type": "bearer",
            "bearer": [{"key": "token", "value": "super-secret-token-value", "type": "string"}],
        }
    )

    normalized = PostmanRequestNormalizer().normalize(request)

    assert "super-secret-token-value" not in repr(normalized)
    assert "super-secret-token-value" not in str(normalized)
    assert normalized.auth.has_sensitive_values is True
