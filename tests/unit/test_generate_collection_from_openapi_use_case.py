import json
from pathlib import Path

from api_quality_agent.adapters.filesystem import LocalArtifactRepository
from api_quality_agent.application.orchestration import AgentOrchestrator
from api_quality_agent.application.use_cases import (
    GenerateCollectionFromOpenApiUseCase,
    GenerateTestsFromDocumentUseCase,
)
from api_quality_agent.domain.models import (
    ApiSpecification,
    ApiSpecificationType,
    Endpoint,
    MediaTypeDefinition,
    ResponseDefinition,
)
from api_quality_agent.domain.services import (
    ApiAnalysisEngine,
    DiffEngine,
    ManagedBlockMerger,
    SchemaInferenceEngine,
    TestStrategyEngine,
)
from api_quality_agent.generators import PostmanTestGenerator
from api_quality_agent.parsers import (
    OpenApiCollectionConverter,
    PostmanCollectionParser,
    PostmanCollectionSerializer,
)


def _real_orchestrator() -> AgentOrchestrator:
    return AgentOrchestrator(
        ApiAnalysisEngine(),
        SchemaInferenceEngine(),
        TestStrategyEngine(),
        PostmanTestGenerator(),
        ManagedBlockMerger(),
        DiffEngine(),
    )


def _specification() -> ApiSpecification:
    endpoint = Endpoint(
        method="GET",
        path="/pets/{petId}",
        operation_id="getPet",
        summary="Busca um pet",
        parameters=(),
        request=None,
        responses=(
            ResponseDefinition(
                status_code="200",
                description="OK",
                media_types=(
                    MediaTypeDefinition(
                        content_type="application/json",
                        schema={"type": "object", "properties": {"id": {"type": "integer"}}},
                        example={"id": 1, "name": "Rex"},
                    ),
                ),
            ),
        ),
        security_requirement_names=(),
    )
    return ApiSpecification(
        spec_type=ApiSpecificationType.OPENAPI,
        spec_version="3.0.0",
        title="Pets API",
        api_version="1.0",
        servers=("https://api.exemplo.com/v1",),
        endpoints=(endpoint,),
        security_schemes=(),
    )


def _build_use_case(tmp_path):
    artifact_repository = LocalArtifactRepository(tmp_path / "artifacts")
    generate_from_document_use_case = GenerateTestsFromDocumentUseCase(
        _real_orchestrator(), artifact_repository
    )
    return GenerateCollectionFromOpenApiUseCase(
        OpenApiCollectionConverter(),
        generate_from_document_use_case,
        PostmanCollectionSerializer(),
        artifact_repository,
    )


def test_generates_a_real_pm_test_script_from_a_response_example(tmp_path):
    use_case = _build_use_case(tmp_path)

    result = use_case.execute(specification=_specification())

    scripts = [outcome for outcome in result.endpoint_outcomes if outcome.generated_script is not None]
    assert len(scripts) == 1
    assert "pm.test(" in scripts[0].generated_script.script
    assert "200" in scripts[0].generated_script.script


def test_saves_a_collection_json_artifact_alongside_scripts_and_diff(tmp_path):
    use_case = _build_use_case(tmp_path)

    result = use_case.execute(specification=_specification())

    categories = {Path(location.path).parent.name for location in result.artifact_locations}
    assert "collection" in categories
    assert "scripts" in categories
    assert "diffs" in categories


def test_round_trip_collection_json_reparses_with_the_same_method_and_path(tmp_path):
    use_case = _build_use_case(tmp_path)

    result = use_case.execute(specification=_specification())

    collection_location = next(
        location for location in result.artifact_locations if "collection.json" in location.path
    )
    saved = json.loads(Path(collection_location.path).read_text(encoding="utf-8"))

    reparsed = PostmanCollectionParser().parse(
        _resolved_input(json.dumps(saved), name="collection.json")
    )
    assert len(reparsed.items) == 1
    request = reparsed.items[0]
    assert request.method == "GET"

    engine = ApiAnalysisEngine()
    analyzed = engine.analyze_collection_requests(reparsed)
    assert len(analyzed) == 1
    # "v1" vem do path do próprio server da spec (https://api.exemplo.com/v1) —
    # faz parte da URL completa, não só do endpoint.
    assert analyzed[0].analysis.path == "/v1/pets/:petId"

    # o script gerado precisa ter sido preservado no JSON reaberto, não perdido.
    request_dict = saved["item"][0]
    events = request_dict.get("event", [])
    test_event = next((event for event in events if event.get("listen") == "test"), None)
    assert test_event is not None
    assert "pm.test(" in "\n".join(test_event["script"]["exec"])


def _resolved_input(content: str, *, name: str):
    from api_quality_agent.domain.models import InputOrigin, ResolvedInput

    return ResolvedInput(origin=InputOrigin.FILE, content_type="json", name=name, content=content)
