import copy
from typing import Any

from api_quality_agent.domain.models import (
    CollectionEvent,
    CollectionFolder,
    CollectionItem,
    CollectionRequest,
    PostmanCollectionDocument,
)


class PostmanCollectionSerializer:
    # Espelha PostmanCollectionParser em sentido inverso. Eventos e examples
    # são reconstruídos a partir do campo `raw` preservado durante o parsing
    # (ou reescrito pelo AgentOrchestrator ao aplicar um bloco gerenciado),
    # garantindo que o formato de saída seja sempre o aceito pela API.
    def serialize(self, document: PostmanCollectionDocument) -> dict[str, Any]:
        info: dict[str, Any] = {"name": document.name}
        if document.postman_id:
            info["_postman_id"] = document.postman_id
        if document.description is not None:
            info["description"] = document.description
        if document.schema:
            info["schema"] = document.schema

        result: dict[str, Any] = {
            "info": info,
            "item": [self._serialize_item(item) for item in document.items],
        }
        if document.variables:
            result["variable"] = [copy.deepcopy(variable) for variable in document.variables]
        if document.auth is not None:
            result["auth"] = copy.deepcopy(document.auth)
        if document.events:
            result["event"] = [self._serialize_event(event) for event in document.events]
        return result

    def _serialize_item(self, item: CollectionItem) -> dict[str, Any]:
        if isinstance(item, CollectionFolder):
            return self._serialize_folder(item)
        if isinstance(item, CollectionRequest):
            return self._serialize_request(item)
        return copy.deepcopy(item.raw)

    def _serialize_folder(self, folder: CollectionFolder) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": folder.name,
            "item": [self._serialize_item(child) for child in folder.items],
        }
        if folder.description is not None:
            result["description"] = folder.description
        if folder.auth is not None:
            result["auth"] = copy.deepcopy(folder.auth)
        if folder.events:
            result["event"] = [self._serialize_event(event) for event in folder.events]
        return result

    def _serialize_request(self, request: CollectionRequest) -> dict[str, Any]:
        request_body: dict[str, Any] = {}
        if request.method is not None:
            request_body["method"] = request.method
        if request.url is not None:
            request_body["url"] = copy.deepcopy(request.url)
        if request.headers:
            request_body["header"] = [copy.deepcopy(header) for header in request.headers]
        if request.body is not None:
            request_body["body"] = copy.deepcopy(request.body)
        if request.auth is not None:
            request_body["auth"] = copy.deepcopy(request.auth)
        if request.description is not None:
            request_body["description"] = request.description

        result: dict[str, Any] = {"name": request.name, "request": request_body}
        if request.item_id is not None:
            result["id"] = request.item_id
        if request.events:
            result["event"] = [self._serialize_event(event) for event in request.events]
        if request.examples:
            result["response"] = [copy.deepcopy(example.raw) for example in request.examples]
        return result

    @staticmethod
    def _serialize_event(event: CollectionEvent) -> dict[str, Any]:
        return copy.deepcopy(event.raw)
