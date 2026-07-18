import hashlib
import json

from api_quality_agent.adapters.postman.postman_api_client import PostmanApiClient
from api_quality_agent.domain.exceptions import IntegrationError
from api_quality_agent.domain.models import (
    CollectionRef,
    CollectionUpdateReceipt,
    PostmanCollectionDocument,
)
from api_quality_agent.domain.policies import ensure_non_empty_id
from api_quality_agent.parsers import PostmanCollectionParser, PostmanCollectionSerializer


class PostmanCollectionRepository:
    def __init__(
        self,
        client: PostmanApiClient,
        parser: PostmanCollectionParser | None = None,
        serializer: PostmanCollectionSerializer | None = None,
    ) -> None:
        self._client = client
        self._parser = parser or PostmanCollectionParser()
        self._serializer = serializer or PostmanCollectionSerializer()

    def list(self, workspace_id: str) -> tuple[CollectionRef, ...]:
        ensure_non_empty_id(workspace_id, "workspace_id")

        payload = self._client.get(f"/collections?workspace={workspace_id}")
        raw_collections = payload.get("collections") if isinstance(payload, dict) else None
        if not isinstance(raw_collections, list):
            raise IntegrationError(
                "Resposta inválida da API do Postman ao listar Collections."
            )

        collections = []
        for item in raw_collections:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                continue
            identifier = item.get("uid") or item.get("id")
            if not isinstance(identifier, str) or not identifier:
                continue
            collections.append(
                CollectionRef(id=identifier, name=item["name"], workspace_id=workspace_id)
            )
        return tuple(collections)

    def get(self, collection_id: str) -> PostmanCollectionDocument:
        ensure_non_empty_id(collection_id, "collection_id")

        payload = self._client.get(f"/collections/{collection_id}")
        raw_collection = payload.get("collection") if isinstance(payload, dict) else None
        if not isinstance(raw_collection, dict):
            raise IntegrationError(
                "Resposta inválida da API do Postman ao obter a Collection."
            )

        return self._parser.parse_text(
            json.dumps(raw_collection), source_name=f"postman:{collection_id}"
        )

    def update(
        self, collection_id: str, document: PostmanCollectionDocument
    ) -> CollectionUpdateReceipt:
        ensure_non_empty_id(collection_id, "collection_id")

        body = {"collection": self._serializer.serialize(document)}
        # Hash calculado sobre os mesmos bytes que serão enviados (o cliente
        # serializa `body` de forma determinística), permitindo comprovar que
        # a mesma entrada sempre produz o mesmo payload, sem persistir o
        # documento em si no resultado.
        document_hash = hashlib.sha256(json.dumps(body).encode("utf-8")).hexdigest()

        response = self._client.put(f"/collections/{collection_id}", body)

        response_body = response.body
        raw_collection = response_body.get("collection") if isinstance(response_body, dict) else None
        if not isinstance(raw_collection, dict):
            raise IntegrationError(
                "Resposta inválida da API do Postman ao atualizar a Collection."
            )

        confirmed_id = raw_collection.get("uid") or raw_collection.get("id")
        if not isinstance(confirmed_id, str) or not confirmed_id:
            raise IntegrationError(
                "Resposta inválida da API do Postman ao atualizar a Collection "
                "(identificador ausente)."
            )

        return CollectionUpdateReceipt(
            confirmed_collection_id=confirmed_id,
            status_code=response.status_code,
            request_id=response.request_id,
            document_hash=document_hash,
        )
