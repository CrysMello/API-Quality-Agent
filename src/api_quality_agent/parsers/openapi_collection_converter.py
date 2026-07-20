import json
import re
import urllib.parse
from typing import Any

from api_quality_agent.domain.models import (
    ApiSpecification,
    CollectionExample,
    CollectionRequest,
    Endpoint,
    Parameter,
    ParameterLocation,
    PostmanCollectionDocument,
)

_PATH_VARIABLE_PATTERN = re.compile(r"\{([^{}]+)\}")
_COLLECTION_SCHEMA_URL = "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"


class OpenApiCollectionConverter:
    # Converte uma ApiSpecification (OpenAPI/Swagger, já parseada) numa
    # PostmanCollectionDocument sintética, reaproveitando sem alterações todo
    # o pipeline de geração de testes existente (que só entende o modelo de
    # Collection do Postman). Puro: sem I/O, sem estado.
    def convert(self, specification: ApiSpecification) -> PostmanCollectionDocument:
        warnings: list[str] = []

        base_url = specification.servers[0] if specification.servers else ""
        if not base_url:
            warnings.append(
                "Nenhum servidor (servers/host) definido na especificação; "
                "as URLs geradas terão base vazia."
            )

        items = tuple(self._convert_endpoint(endpoint, base_url) for endpoint in specification.endpoints)

        return PostmanCollectionDocument(
            postman_id=None,
            name=specification.title or "Coleção gerada a partir de OpenAPI",
            description=None,
            schema=_COLLECTION_SCHEMA_URL,
            items=items,
            variables=(),
            auth=None,
            events=(),
            warnings=tuple(warnings),
        )

    def _convert_endpoint(self, endpoint: Endpoint, base_url: str) -> CollectionRequest:
        url = self._build_url(endpoint, base_url)

        return CollectionRequest(
            item_id=endpoint.operation_id,
            name=endpoint.summary or endpoint.operation_id or f"{endpoint.method} {endpoint.path}",
            description=None,
            method=endpoint.method,
            url=url,
            url_raw=str(url.get("raw")) if url.get("raw") is not None else None,
            headers=self._build_headers(endpoint),
            body=self._build_body(endpoint),
            auth=None,
            events=(),
            examples=self._build_examples(endpoint),
        )

    def _build_url(self, endpoint: Endpoint, base_url: str) -> dict[str, Any]:
        parsed_base = urllib.parse.urlsplit(base_url)
        protocol = parsed_base.scheme or None
        host = tuple(segment for segment in parsed_base.netloc.split(".") if segment)
        base_path_segments = [segment for segment in parsed_base.path.split("/") if segment]

        endpoint_segments = [
            _PATH_VARIABLE_PATTERN.sub(r":\1", segment)
            for segment in endpoint.path.split("/")
            if segment
        ]
        path_segments = base_path_segments + endpoint_segments

        query_parameters = [
            parameter for parameter in endpoint.parameters if parameter.location is ParameterLocation.QUERY
        ]
        path_parameters = {
            parameter.name: parameter
            for parameter in endpoint.parameters
            if parameter.location is ParameterLocation.PATH
        }

        raw = base_url.rstrip("/") + "/" + "/".join(endpoint_segments) if endpoint_segments else base_url
        if query_parameters:
            raw += "?" + urllib.parse.urlencode(
                {parameter.name: _example_as_str(parameter.example) for parameter in query_parameters}
            )

        url: dict[str, Any] = {
            "raw": raw,
            "protocol": protocol,
            "host": list(host),
            "path": path_segments,
            "query": [
                {
                    "key": parameter.name,
                    "value": _example_as_str(parameter.example),
                    "disabled": False,
                }
                for parameter in query_parameters
            ],
            "variable": [
                {
                    "key": name,
                    "value": _example_as_str(path_parameters[name].example) if name in path_parameters else "",
                }
                for name in _path_variable_names(endpoint.path)
            ],
        }
        return url

    def _build_headers(self, endpoint: Endpoint) -> tuple[dict[str, Any], ...]:
        return tuple(
            {"key": parameter.name, "value": _example_as_str(parameter.example), "disabled": False}
            for parameter in endpoint.parameters
            if parameter.location is ParameterLocation.HEADER
        )

    def _build_body(self, endpoint: Endpoint) -> dict[str, Any] | None:
        if endpoint.request is None:
            return None
        for media_type in endpoint.request.media_types:
            if media_type.example is not None:
                return {
                    "mode": "raw",
                    "raw": json.dumps(media_type.example, ensure_ascii=False),
                    "options": {"raw": {"language": "json"}},
                }
        return None

    def _build_examples(self, endpoint: Endpoint) -> tuple[CollectionExample, ...]:
        examples: list[CollectionExample] = []
        for response in endpoint.responses:
            media_type = next(
                (media_type for media_type in response.media_types if media_type.example is not None),
                None,
            )
            if media_type is None:
                continue

            code = int(response.status_code) if response.status_code.isdigit() else None
            body_text = json.dumps(media_type.example, ensure_ascii=False)
            name = f"{endpoint.method} {endpoint.path} - {response.status_code}"

            examples.append(
                CollectionExample(
                    name=name,
                    status=None,
                    code=code,
                    headers=(),
                    body=body_text,
                    raw={
                        "name": name,
                        "originalRequest": {"method": endpoint.method},
                        "status": "",
                        "code": code,
                        "header": [],
                        "body": body_text,
                    },
                )
            )
        return tuple(examples)


def _path_variable_names(path: str) -> list[str]:
    seen: dict[str, None] = {}
    for match in _PATH_VARIABLE_PATTERN.finditer(path):
        seen.setdefault(match.group(1), None)
    return list(seen)


def _example_as_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)
