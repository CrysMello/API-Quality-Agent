import json

from api_quality_agent.application.orchestration.collection_generation_result import (
    CollectionGenerationResult,
)
from api_quality_agent.application.orchestration.endpoint_generation_outcome import (
    EndpointGenerationOutcome,
)
from api_quality_agent.domain.exceptions import ApiQualityAgentError
from api_quality_agent.domain.models import (
    AnalyzedCollectionRequest,
    CollectionEvent,
    CollectionFolder,
    CollectionItem,
    CollectionRequest,
    ExecutionContext,
    PostmanCollectionDocument,
    SchemaInferenceWarning,
)
from api_quality_agent.domain.services import (
    ApiAnalysisEngine,
    DiffEngine,
    ManagedBlockMerger,
    SchemaInferenceEngine,
    TestStrategyEngine,
)
from api_quality_agent.generators import GeneratedTestScript, PostmanTestGenerator

DEFAULT_MANAGED_BLOCK_ID = "api-quality-agent-tests"


class AgentOrchestrator:
    def __init__(
        self,
        analysis_engine: ApiAnalysisEngine,
        schema_inference_engine: SchemaInferenceEngine,
        test_strategy_engine: TestStrategyEngine,
        test_generator: PostmanTestGenerator,
        managed_block_merger: ManagedBlockMerger,
        diff_engine: DiffEngine,
        *,
        managed_block_id: str = DEFAULT_MANAGED_BLOCK_ID,
    ) -> None:
        self._analysis_engine = analysis_engine
        self._schema_inference_engine = schema_inference_engine
        self._test_strategy_engine = test_strategy_engine
        self._test_generator = test_generator
        self._managed_block_merger = managed_block_merger
        self._diff_engine = diff_engine
        self._managed_block_id = managed_block_id

    def process(
        self,
        document: PostmanCollectionDocument,
        execution_context: ExecutionContext,
    ) -> CollectionGenerationResult:
        analyzed_requests = self._analysis_engine.analyze_collection_requests(document)
        analysis_result = self._analysis_engine.analyze_collection(document)

        endpoint_outcomes: list[EndpointGenerationOutcome] = []
        replacements: dict[int, CollectionRequest] = {}

        for index, analyzed in enumerate(analyzed_requests):
            outcome, updated_request = self._process_endpoint(analyzed, execution_context)
            endpoint_outcomes.append(outcome)
            if updated_request is not None:
                replacements[index] = updated_request

        modified_document = _rebuild_document_with_replacements(document, replacements)
        diff = self._diff_engine.compare(document, modified_document)

        return CollectionGenerationResult(
            execution_context=execution_context,
            analysis_warnings=analysis_result.warnings,
            dependencies=analysis_result.dependencies,
            endpoint_outcomes=tuple(endpoint_outcomes),
            diff=diff,
            artifact_locations=(),
        )

    def _process_endpoint(
        self,
        analyzed: AnalyzedCollectionRequest,
        execution_context: ExecutionContext,
    ) -> tuple[EndpointGenerationOutcome, CollectionRequest | None]:
        raw_request = analyzed.raw_request
        endpoint_analysis = analyzed.analysis

        try:
            response_schema, schema_warnings = self._infer_response_schema(raw_request)

            strategy = self._test_strategy_engine.build_strategy(
                endpoint_analysis, response_schema=response_schema
            )
            generated_script = self._test_generator.generate(strategy)

            updated_request = self._apply_managed_block(raw_request, generated_script)
            merged_script = _extract_test_script_text(updated_request)

            outcome = EndpointGenerationOutcome(
                endpoint_source=endpoint_analysis.source,
                generated_script=generated_script,
                merged_script=merged_script,
                schema_warnings=schema_warnings,
                strategy_warnings=strategy.warnings,
                error=None,
            )
            return outcome, updated_request
        except ApiQualityAgentError as exc:
            # Política adotada: resultado parcial. Uma falha ao processar um
            # request específico não interrompe os demais — fica registrada
            # com contexto (endpoint + mensagem), e o processamento continua.
            execution_context.add_warning(
                f"Falha ao processar '{endpoint_analysis.source}': {exc}"
            )
            outcome = EndpointGenerationOutcome(
                endpoint_source=endpoint_analysis.source,
                generated_script=None,
                merged_script=None,
                schema_warnings=(),
                strategy_warnings=(),
                error=str(exc),
            )
            return outcome, None

    def _infer_response_schema(
        self, raw_request: CollectionRequest
    ) -> tuple[dict | None, tuple[SchemaInferenceWarning, ...]]:
        parsed_examples = []
        for example in raw_request.examples:
            if not example.body:
                continue
            try:
                parsed_examples.append(json.loads(example.body))
            except json.JSONDecodeError:
                continue  # example salvo não é JSON: ignorado, não é um erro fatal

        if not parsed_examples:
            return None, ()

        schema_result = self._schema_inference_engine.infer(parsed_examples)
        return schema_result.schema, schema_result.warnings

    def _apply_managed_block(
        self, raw_request: CollectionRequest, generated_script: GeneratedTestScript
    ) -> CollectionRequest:
        existing_test_event = next(
            (event for event in raw_request.events if event.listen == "test"), None
        )
        existing_text = (
            "\n".join(existing_test_event.exec_lines) if existing_test_event is not None else ""
        )

        merge_result = self._managed_block_merger.merge(
            existing_text, self._managed_block_id, generated_script.script
        )

        new_exec_lines = tuple(merge_result.text.split("\n"))
        if new_exec_lines and new_exec_lines[-1] == "":
            new_exec_lines = new_exec_lines[:-1]

        script_type = existing_test_event.script_type if existing_test_event else "text/javascript"
        new_test_event = CollectionEvent(
            listen="test",
            exec_lines=new_exec_lines,
            script_type=script_type,
            raw={
                "listen": "test",
                "script": {"type": script_type, "exec": list(new_exec_lines)},
            },
        )

        if existing_test_event is None:
            new_events = raw_request.events + (new_test_event,)
        else:
            new_events = tuple(
                new_test_event if event.listen == "test" else event
                for event in raw_request.events
            )

        return CollectionRequest(
            item_id=raw_request.item_id,
            name=raw_request.name,
            description=raw_request.description,
            method=raw_request.method,
            url=raw_request.url,
            url_raw=raw_request.url_raw,
            headers=raw_request.headers,
            body=raw_request.body,
            auth=raw_request.auth,
            events=new_events,
            examples=raw_request.examples,
        )


def _extract_test_script_text(request: CollectionRequest) -> str | None:
    test_event = next((event for event in request.events if event.listen == "test"), None)
    if test_event is None:
        return None
    return "\n".join(test_event.exec_lines)


def _rebuild_document_with_replacements(
    document: PostmanCollectionDocument,
    replacements: dict[int, CollectionRequest],
) -> PostmanCollectionDocument:
    counter = [0]
    items = _rebuild_items(document.items, replacements, counter)
    return PostmanCollectionDocument(
        postman_id=document.postman_id,
        name=document.name,
        description=document.description,
        schema=document.schema,
        items=items,
        variables=document.variables,
        auth=document.auth,
        events=document.events,
        warnings=document.warnings,
    )


def _rebuild_items(
    items: tuple[CollectionItem, ...],
    replacements: dict[int, CollectionRequest],
    counter: list[int],
) -> tuple[CollectionItem, ...]:
    rebuilt: list[CollectionItem] = []
    for item in items:
        if isinstance(item, CollectionFolder):
            rebuilt.append(
                CollectionFolder(
                    name=item.name,
                    description=item.description,
                    items=_rebuild_items(item.items, replacements, counter),
                    auth=item.auth,
                    events=item.events,
                )
            )
        elif isinstance(item, CollectionRequest):
            index = counter[0]
            counter[0] += 1
            rebuilt.append(replacements.get(index, item))
        else:
            rebuilt.append(item)
    return tuple(rebuilt)
