from api_quality_agent.adapters.postman.postman_api_client import PostmanApiClient
from api_quality_agent.domain.exceptions import IntegrationError
from api_quality_agent.domain.models import WorkspaceRef


class PostmanWorkspaceRepository:
    def __init__(self, client: PostmanApiClient) -> None:
        self._client = client

    def list(self) -> tuple[WorkspaceRef, ...]:
        payload = self._client.get("/workspaces")
        raw_workspaces = payload.get("workspaces") if isinstance(payload, dict) else None
        if not isinstance(raw_workspaces, list):
            raise IntegrationError(
                "Resposta inválida da API do Postman ao listar Workspaces."
            )

        return tuple(
            WorkspaceRef(id=item["id"], name=item["name"])
            for item in raw_workspaces
            if isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and isinstance(item.get("name"), str)
        )
