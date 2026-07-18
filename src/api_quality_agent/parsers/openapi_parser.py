import json
from typing import Any

import yaml

from api_quality_agent.domain.exceptions import (
    InvalidApiSpecificationError,
    UnsupportedSpecificationVersionError,
)
from api_quality_agent.domain.models import (
    ApiSpecification,
    ApiSpecificationType,
    Endpoint,
    MediaTypeDefinition,
    Parameter,
    ParameterLocation,
    RequestDefinition,
    ResolvedInput,
    ResponseDefinition,
    SecurityDefinition,
)
from api_quality_agent.parsers.reference_resolver import ReferenceResolver

_HTTP_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})

_SWAGGER2_PARAMETER_SCHEMA_KEYS = (
    "type",
    "format",
    "items",
    "enum",
    "default",
    "minimum",
    "maximum",
    "minLength",
    "maxLength",
    "pattern",
    "collectionFormat",
    "uniqueItems",
    "multipleOf",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minItems",
    "maxItems",
)


class OpenApiParser:
    def parse(self, resolved_input: ResolvedInput) -> ApiSpecification:
        return self.parse_text(resolved_input.content, source_name=resolved_input.name)

    def parse_text(self, text: str, *, source_name: str = "<content>") -> ApiSpecification:
        document = _load_document(text, source_name=source_name)
        spec_type, spec_version = _determine_spec_type_and_version(document, source_name=source_name)

        resolver = ReferenceResolver(document)
        resolved_document = resolver.resolve(document)

        info = resolved_document.get("info") or {}
        title = info.get("title") if isinstance(info, dict) else None
        api_version = info.get("version") if isinstance(info, dict) else None

        return ApiSpecification(
            spec_type=spec_type,
            spec_version=spec_version,
            title=title,
            api_version=api_version,
            servers=_extract_servers(resolved_document, spec_type),
            endpoints=_extract_endpoints(resolved_document, spec_type),
            security_schemes=_extract_security_schemes(resolved_document, spec_type),
            warnings=resolver.warnings,
        )


def _load_document(text: str, *, source_name: str) -> dict[str, Any]:
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        try:
            document = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise InvalidApiSpecificationError(
                f"Documento não é um JSON nem YAML válido: {source_name}: {exc}"
            ) from exc

    if not isinstance(document, dict):
        raise InvalidApiSpecificationError(
            f"Documento OpenAPI/Swagger deve ser um objeto no nível raiz: {source_name}"
        )
    return document


def _determine_spec_type_and_version(
    document: dict[str, Any], *, source_name: str
) -> tuple[ApiSpecificationType, str]:
    openapi_version = document.get("openapi")
    if isinstance(openapi_version, str):
        if not (openapi_version.startswith("3.0") or openapi_version.startswith("3.1")):
            raise UnsupportedSpecificationVersionError(
                f"Versão OpenAPI não suportada em {source_name}: {openapi_version!r}"
            )
        return ApiSpecificationType.OPENAPI, openapi_version

    swagger_version = document.get("swagger")
    if isinstance(swagger_version, str):
        if swagger_version != "2.0":
            raise UnsupportedSpecificationVersionError(
                f"Versão Swagger não suportada em {source_name}: {swagger_version!r}"
            )
        return ApiSpecificationType.SWAGGER, swagger_version

    raise InvalidApiSpecificationError(
        f"Documento não contém a chave 'openapi' nem 'swagger' no nível raiz: {source_name}"
    )


def _extract_servers(document: dict[str, Any], spec_type: ApiSpecificationType) -> tuple[str, ...]:
    if spec_type is ApiSpecificationType.OPENAPI:
        servers = document.get("servers") or []
        return tuple(
            server["url"]
            for server in servers
            if isinstance(server, dict) and isinstance(server.get("url"), str)
        )

    host = document.get("host")
    if not isinstance(host, str) or not host:
        return ()
    base_path = document.get("basePath") or ""
    schemes = document.get("schemes") or []
    if not schemes:
        return (f"{host}{base_path}",)
    return tuple(f"{scheme}://{host}{base_path}" for scheme in schemes)


def _extract_security_schemes(
    document: dict[str, Any], spec_type: ApiSpecificationType
) -> tuple[SecurityDefinition, ...]:
    if spec_type is ApiSpecificationType.OPENAPI:
        components = document.get("components") or {}
        raw_schemes = components.get("securitySchemes") or {} if isinstance(components, dict) else {}
    else:
        raw_schemes = document.get("securityDefinitions") or {}

    definitions = []
    for name, raw in raw_schemes.items():
        if not isinstance(raw, dict):
            continue
        scheme_type = raw.get("type")
        if not isinstance(scheme_type, str) or not scheme_type:
            continue
        definitions.append(
            SecurityDefinition(
                name=name,
                type=scheme_type,
                scheme=raw.get("scheme"),
                location=raw.get("in"),
                parameter_name=raw.get("name"),
                description=raw.get("description"),
            )
        )
    return tuple(definitions)


def _extract_endpoints(document: dict[str, Any], spec_type: ApiSpecificationType) -> tuple[Endpoint, ...]:
    paths = document.get("paths") or {}
    endpoints: list[Endpoint] = []
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        path_level_parameters = path_item.get("parameters") or []
        for method, operation in path_item.items():
            if method.lower() not in _HTTP_METHODS or not isinstance(operation, dict):
                continue
            endpoints.append(
                _build_endpoint(
                    path=path,
                    method=method.upper(),
                    operation=operation,
                    path_level_parameters=path_level_parameters,
                    document=document,
                    spec_type=spec_type,
                )
            )
    return tuple(endpoints)


def _build_endpoint(
    *,
    path: str,
    method: str,
    operation: dict[str, Any],
    path_level_parameters: list[Any],
    document: dict[str, Any],
    spec_type: ApiSpecificationType,
) -> Endpoint:
    raw_parameters = _merge_parameters(path_level_parameters, operation.get("parameters") or [])

    body_parameter = None
    if spec_type is ApiSpecificationType.SWAGGER:
        body_parameter = next((p for p in raw_parameters if p.get("in") == "body"), None)

    parameters = _extract_parameters(raw_parameters, spec_type)

    if spec_type is ApiSpecificationType.OPENAPI:
        request = _extract_request_openapi3(operation)
        responses = _extract_responses_openapi3(operation)
    else:
        request = _extract_request_swagger2(operation, document, body_parameter)
        responses = _extract_responses_swagger2(operation, document)

    return Endpoint(
        method=method,
        path=path,
        operation_id=operation.get("operationId"),
        summary=operation.get("summary"),
        parameters=parameters,
        request=request,
        responses=responses,
        security_requirement_names=_extract_security_requirement_names(operation, document),
    )


def _merge_parameters(
    path_level: list[Any], operation_level: list[Any]
) -> list[dict[str, Any]]:
    merged: dict[tuple[Any, Any], dict[str, Any]] = {}
    for raw in (*path_level, *operation_level):
        if not isinstance(raw, dict):
            continue
        key = (raw.get("name"), raw.get("in"))
        merged[key] = raw
    return list(merged.values())


def _extract_parameters(
    raw_parameters: list[dict[str, Any]], spec_type: ApiSpecificationType
) -> tuple[Parameter, ...]:
    parameters: list[Parameter] = []
    for raw in raw_parameters:
        location = raw.get("in")
        if location == "body":
            continue
        name = raw.get("name")
        if not isinstance(name, str) or not name or not isinstance(location, str):
            continue

        if spec_type is ApiSpecificationType.OPENAPI:
            schema = raw.get("schema")
            example = raw.get("example")
        else:
            schema = _build_swagger2_parameter_schema(raw)
            example = None

        parameters.append(
            Parameter(
                name=name,
                location=ParameterLocation(location),
                required=bool(raw.get("required", False)),
                schema=schema,
                description=raw.get("description"),
                example=example,
            )
        )
    return tuple(parameters)


def _build_swagger2_parameter_schema(parameter: dict[str, Any]) -> dict[str, Any] | None:
    schema = {key: parameter[key] for key in _SWAGGER2_PARAMETER_SCHEMA_KEYS if key in parameter}
    return schema or None


def _extract_request_openapi3(operation: dict[str, Any]) -> RequestDefinition | None:
    request_body = operation.get("requestBody")
    if not isinstance(request_body, dict):
        return None
    content = request_body.get("content") or {}
    return RequestDefinition(
        required=bool(request_body.get("required", False)),
        description=request_body.get("description"),
        media_types=_extract_media_types_from_content(content),
    )


def _extract_request_swagger2(
    operation: dict[str, Any],
    document: dict[str, Any],
    body_parameter: dict[str, Any] | None,
) -> RequestDefinition | None:
    if body_parameter is None:
        return None
    consumes = operation.get("consumes", document.get("consumes", []))
    schema = body_parameter.get("schema")
    media_types = tuple(
        MediaTypeDefinition(content_type=content_type, schema=schema, example=None)
        for content_type in consumes
        if isinstance(content_type, str)
    )
    return RequestDefinition(
        required=bool(body_parameter.get("required", False)),
        description=body_parameter.get("description"),
        media_types=media_types,
    )


def _extract_responses_openapi3(operation: dict[str, Any]) -> tuple[ResponseDefinition, ...]:
    responses = operation.get("responses") or {}
    result = []
    for status_code, response_obj in responses.items():
        if not isinstance(response_obj, dict):
            continue
        content = response_obj.get("content") or {}
        result.append(
            ResponseDefinition(
                status_code=str(status_code),
                description=response_obj.get("description"),
                media_types=_extract_media_types_from_content(content),
            )
        )
    return tuple(result)


def _extract_responses_swagger2(
    operation: dict[str, Any], document: dict[str, Any]
) -> tuple[ResponseDefinition, ...]:
    responses = operation.get("responses") or {}
    produces = operation.get("produces", document.get("produces", []))
    result = []
    for status_code, response_obj in responses.items():
        if not isinstance(response_obj, dict):
            continue
        schema = response_obj.get("schema")
        examples = response_obj.get("examples") or {}
        media_types = tuple(
            MediaTypeDefinition(
                content_type=content_type,
                schema=schema,
                example=examples.get(content_type),
            )
            for content_type in produces
            if isinstance(content_type, str)
        )
        result.append(
            ResponseDefinition(
                status_code=str(status_code),
                description=response_obj.get("description"),
                media_types=media_types,
            )
        )
    return tuple(result)


def _extract_media_types_from_content(content: dict[str, Any]) -> tuple[MediaTypeDefinition, ...]:
    return tuple(
        MediaTypeDefinition(
            content_type=content_type,
            schema=media_type_obj.get("schema") if isinstance(media_type_obj, dict) else None,
            example=media_type_obj.get("example") if isinstance(media_type_obj, dict) else None,
        )
        for content_type, media_type_obj in content.items()
    )


def _extract_security_requirement_names(
    operation: dict[str, Any], document: dict[str, Any]
) -> tuple[str, ...]:
    security = operation.get("security", document.get("security", []))
    names: list[str] = []
    for requirement in security or []:
        if isinstance(requirement, dict):
            names.extend(requirement.keys())
    return tuple(names)
