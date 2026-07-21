import re
from collections.abc import Mapping
from typing import Any

from api_quality_agent.domain.exceptions import InputError, InvalidPostmanCollectionError
from api_quality_agent.domain.models import CanonicalEndpoint

# R2-04: CanonicalEndpointNormalizer — transforma diferentes representações
# de um endpoint (request real do Postman ou path declarado numa planilha de
# contrato) numa única representação canônica: método + path, com
# parâmetros de qualquer formato de origem ({id} / :id / {{id}}) sempre
# normalizados pro mesmo token "{param}" (posição importa, nome não).
#
# Nunca resolve variável de infraestrutura (usa url.path preferencialmente,
# que já exclui host/protocolo estruturalmente), nunca analisa query string
# além de descartá-la, nunca acessa arquivo Excel.
#
# collection_path_prefix (--collection-path-prefix): prefixo fixo de path
# (ex.: de gateway) presente só nas requests reais da Collection, ausente do
# path declarado no contrato. Removido por correspondência exata de
# segmentos no início do path — nunca por comparação textual (startswith),
# nunca em ocorrências internas. Aplicado só em normalize_collection_request;
# normalize_declared_endpoint nunca é afetado.

_SCHEME_HOST_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://[^/]*")
_LEADING_VARIABLE_TOKEN_PATTERN = re.compile(r"^\{\{\s*[^{}]+\s*\}\}")
_DOUBLE_BRACE_PARAM = re.compile(r"^\{\{\s*[^{}]+\s*\}\}$")
_SINGLE_BRACE_PARAM = re.compile(r"^\{[^{}]+\}$")
_COLON_PARAM = re.compile(r"^:[^/]+$")

_PARAM_TOKEN = "{param}"


class CanonicalEndpointNormalizer:
    def __init__(self, *, collection_path_prefix: str | None = None) -> None:
        self._collection_path_prefix_segments = _split_prefix_segments(collection_path_prefix)

    def normalize_collection_request(
        self, method: str | None, url: Mapping[str, Any] | str | None
    ) -> CanonicalEndpoint:
        if not method or not method.strip():
            raise InvalidPostmanCollectionError(
                "Método HTTP ausente — não é possível normalizar o endpoint."
            )
        canonical_path = self._extract_canonical_path(url)
        return CanonicalEndpoint(method=method.strip().upper(), canonical_path=canonical_path)

    def normalize_declared_endpoint(self, method: str, path: str) -> CanonicalEndpoint:
        # Nunca recebe collection_path_prefix — o path declarado no contrato
        # não carrega o prefixo da Collection.
        return CanonicalEndpoint(method=method.upper(), canonical_path=_canonicalize_segments(path))

    def _extract_canonical_path(self, url: Mapping[str, Any] | str | None) -> str:
        # Regra de fallback (exatamente como especificado):
        # SE url.path existir e não estiver vazio -> usar url.path.
        # SENÃO, SE url.raw existir -> extrair path de url.raw (ignorando
        # protocolo/domínio/host/query string).
        # SENÃO -> erro de Collection inválida.
        if isinstance(url, Mapping):
            path_value = url.get("path")
            if isinstance(path_value, list):
                segments = [
                    str(segment)
                    for segment in path_value
                    if isinstance(segment, str) and segment.strip()
                ]
                if segments:
                    segments = self._strip_collection_path_prefix(segments)
                    return "/" + "/".join(_normalize_segment(segment) for segment in segments)

            raw_value = url.get("raw")
            if isinstance(raw_value, str) and raw_value.strip():
                return self._canonicalize_collection_segments(_strip_host(raw_value))

            raise InvalidPostmanCollectionError(
                "Não foi possível determinar o path da request: url.path e url.raw ausentes/vazios."
            )

        if isinstance(url, str):
            if not url.strip():
                raise InvalidPostmanCollectionError("URL vazia — não é possível normalizar o endpoint.")
            return self._canonicalize_collection_segments(_strip_host(url))

        raise InvalidPostmanCollectionError("URL ausente ou em formato não suportado.")

    def _canonicalize_collection_segments(self, path: str) -> str:
        path_only = path.split("?", 1)[0]
        segments = [segment for segment in path_only.split("/") if segment]
        segments = self._strip_collection_path_prefix(segments)
        return "/" + "/".join(_normalize_segment(segment) for segment in segments)

    def _strip_collection_path_prefix(self, segments: list[str]) -> list[str]:
        prefix = self._collection_path_prefix_segments
        size = len(prefix)
        if size == 0:
            return segments
        if len(segments) >= size and tuple(segments[:size]) == prefix:
            return segments[size:]
        return segments


def _split_prefix_segments(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    segments = tuple(segment.strip() for segment in value.split("/") if segment.strip())
    if not segments:
        raise InputError(
            f"--collection-path-prefix inválido: '{value}' não contém nenhum segmento de path utilizável."
        )
    return segments


def _strip_host(raw: str) -> str:
    without_scheme = _SCHEME_HOST_PATTERN.sub("", raw, count=1)
    return _LEADING_VARIABLE_TOKEN_PATTERN.sub("", without_scheme, count=1)


def _canonicalize_segments(path: str) -> str:
    path_only = path.split("?", 1)[0]
    segments = [segment for segment in path_only.split("/") if segment]
    return "/" + "/".join(_normalize_segment(segment) for segment in segments)


def _normalize_segment(segment: str) -> str:
    if (
        _DOUBLE_BRACE_PARAM.match(segment)
        or _SINGLE_BRACE_PARAM.match(segment)
        or _COLON_PARAM.match(segment)
    ):
        return _PARAM_TOKEN
    return segment
