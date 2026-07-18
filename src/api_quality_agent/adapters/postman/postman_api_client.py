import json
import urllib.error
import urllib.request
from collections.abc import Callable
from time import sleep as _default_sleep
from typing import Any, NoReturn

from api_quality_agent.domain.exceptions import (
    AuthenticationError,
    IntegrationError,
    ResourceNotFoundError,
)
from api_quality_agent.domain.policies import ensure_non_empty_id

DEFAULT_BASE_URL = "https://api.getpostman.com"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_BACKOFF_SECONDS = 0.5

_TRANSIENT_STATUS_CODES = frozenset({429})


class _TransientRequestError(Exception):
    pass


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
        url = f"{self._base_url}{path}"
        attempt = 0
        while True:
            try:
                return self._perform_request(url)
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

    def _perform_request(self, url: str) -> Any:
        request = urllib.request.Request(
            url,
            headers={"X-Api-Key": self._api_key, "Accept": "application/json"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                raw_body = response.read()
        except urllib.error.HTTPError as exc:
            self._handle_http_error(exc)
        except TimeoutError as exc:
            raise _TransientRequestError("Tempo limite de requisição excedido.") from exc
        except urllib.error.URLError as exc:
            raise _TransientRequestError(f"Falha de rede: {exc.reason}") from exc

        return self._parse_json_body(raw_body)

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
