import json
import re
from dataclasses import replace

from api_quality_agent.application.orchestration import CollectionGenerationResult
from api_quality_agent.application.use_cases.generate_tests_from_document import (
    GenerateTestsFromDocumentUseCase,
)
from api_quality_agent.domain.models import ApiSpecification, GeneratedArtifact
from api_quality_agent.parsers import OpenApiCollectionConverter, PostmanCollectionSerializer
from api_quality_agent.ports.outbound import ArtifactRepository

_UNSAFE_SLUG_CHARS = re.compile(r"[^A-Za-z0-9_.-]+")
_LOCAL_FILE_WORKSPACE_ID = "local"


class GenerateCollectionFromOpenApiUseCase:
    # Compõe sobre GenerateTestsFromDocumentUseCase (já testado, já grava
    # scripts/*.js e diffs/diff.json) em vez de duplicar essa lógica: converte
    # a especificação numa Collection sintética, delega a geração de testes, e
    # só adiciona o passo extra — gravar a Collection completa (já com os
    # testes injetados) como collection.json, pronta pra importar no Postman
    # ou rodar direto via `run --file`.
    def __init__(
        self,
        converter: OpenApiCollectionConverter,
        generate_from_document_use_case: GenerateTestsFromDocumentUseCase,
        collection_serializer: PostmanCollectionSerializer,
        artifact_repository: ArtifactRepository,
    ) -> None:
        self._converter = converter
        self._generate_from_document_use_case = generate_from_document_use_case
        self._collection_serializer = collection_serializer
        self._artifact_repository = artifact_repository

    def execute(self, *, specification: ApiSpecification) -> CollectionGenerationResult:
        document = self._converter.convert(specification)
        result = self._generate_from_document_use_case.execute(document=document)

        serialized = self._collection_serializer.serialize(result.modified_document)
        artifact = GeneratedArtifact(
            category="collection",
            relative_path="collection.json",
            content=json.dumps(serialized, indent=2, ensure_ascii=False),
        )
        location = self._artifact_repository.save(
            workspace_id=_LOCAL_FILE_WORKSPACE_ID,
            collection_id=_slugify(document.name),
            execution_id=result.execution_context.execution_id,
            artifact=artifact,
        )

        return replace(result, artifact_locations=result.artifact_locations + (location,))


def _slugify(value: str) -> str:
    sanitized = _UNSAFE_SLUG_CHARS.sub("_", value).strip("_")
    return sanitized or "collection"
