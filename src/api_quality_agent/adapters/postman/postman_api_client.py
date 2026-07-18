import json
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from email.message import Message
from time import sleep as _default_sleep
from typing import Any, NoReturn

from api_quality_agent.domain.exceptions import (
    AuthenticationError,
    ConflictError,
    IntegrationError,
    ResourceNotFoundError,
)
from api_quality_agent.domain.policies import ensure_non_empty_id

DEFAULT_BASE_URL = "https://api.getpostman.com"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_BACKOFF_SECONDS = 0.5

_TRANSIENT_STATUS_CODES = frozenset({429})
_REQUEST_ID_HEADER_CANDIDATES = ("X-Request-Id", "X-Request-ID", "Postman-Request-Id")


@dataclass(frozen=True)
class PostmanHttpResponse:
    body: Any
    status_code: int
    request_id: str | None


class _TransientRequestError(Exception):
    pass


def _extract_request_id(headers: Message) -> str | None:
    for name in _REQUEST_ID_HEADER_CANDIDATES:
        value = headers.get(name)
        if value:
            return value
    return None


class PostmanApiClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
        sleep_fn: Callable[[float], None] = _default_sleep,
    ) -> None:
        ensure_non_empty_id(api_key, "api_key")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._sleep_fn = sleep_fn

    def get(self, path: str) -> Any:
        return self._request("GET", path).body

    def put(self, path: str, body: dict[str, Any]) -> PostmanHttpResponse:
        return self._request("PUT", path, body=body)

    def _request(
        self, method: str, path: str, *, body: dict[str, Any] | None = None
    ) -> PostmanHttpResponse:
        url = f"{self._base_url}{path}"
        attempt = 0
        while True:
            try:
                return self._perform_request(url, method=method, body=body)
            except _TransientRequestError as exc:
                attempt += 1
                if attempt > self._max_retries:
                    raise IntegrationError(
                        "Falha ao comunicar com a API do Postman após "
                        f"{attempt} tentativa(s): {exc}"
                    ) from exc
                self._sleep_fn(self._retry_backoff_seconds)

    def validate_authentication(self) -> None:
        self.get("/me")

    def _perform_request(
        self, url: str, *, method: str = "GET", body: dict[str, Any] | None = None
    ) -> PostmanHttpResponse:
        headers = {"X-Api-Key": self._api_key, "Accept": "application/json"}
        data: bytes | None = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                raw_body = response.read()
                status_code = response.status
                request_id = _extract_request_id(response.headers)
        except urllib.error.HTTPError as exc:
            self._handle_http_error(exc)
        except TimeoutError as exc:
            raise _TransientRequestError("Tempo limite de requisição excedido.") from exc
        except urllib.error.URLError as exc:
            raise _TransientRequestError(f"Falha de rede: {exc.reason}") from exc

        parsed_body = self._parse_json_body(raw_body)
        return PostmanHttpResponse(
            body=parsed_body, status_code=status_code, request_id=request_id
        )

    def _handle_http_error(self, exc: urllib.error.HTTPError) -> NoReturn:
        status = exc.code

        if status in (401, 403):
            raise AuthenticationError(
                "Falha de autenticação na API do Postman: API Key inválida, ausente ou "
                "sem permissão para este recurso."
            ) from exc
        if status == 404:
            raise ResourceNotFoundError(
                "Recurso não encontrado na API do Postman."
            ) from exc
        if status == 409:
            raise ConflictError(
                "Conflito ao atualizar a Collection na API do Postman (HTTP 409): a versão "
                "remota pode ter sido alterada por outra origem desde a última leitura."
            ) from exc
        if status in _TRANSIENT_STATUS_CODES:
            raise _TransientRequestError(
                f"Limite de requisições da API do Postman excedido (HTTP {status})."
            ) from exc
        if 500 <= status < 600:
            raise _TransientRequestError(
                f"Erro no servidor da API do Postman (HTTP {status})."
            ) from exc

        raise IntegrationError(
            f"Resposta inesperada da API do Postman (HTTP {status})."
        ) from exc

    @staticmethod
    def _parse_json_body(raw_body: bytes) -> Any:
        try:
            return json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise IntegrationError(
                "Resposta inválida recebida da API do Postman (JSON malformado)."
            ) from exc
