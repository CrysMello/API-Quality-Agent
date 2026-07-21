import re
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from api_quality_agent.application.orchestration import AgentOrchestrator, CollectionGenerationResult
from api_quality_agent.application.use_cases.generate_collection_tests import (
    GenerateCollectionTestsUseCase,
)
from api_quality_agent.application.use_cases.generate_tests_from_document import (
    GenerateTestsFromDocumentUseCase,
)
from api_quality_agent.application.use_cases.get_current_workspace import GetCurrentWorkspaceUseCase
from api_quality_agent.application.use_cases.resolve_collection import ResolveCollectionUseCase
from api_quality_agent.domain.exceptions import InputError, InvalidPostmanCollectionError
from api_quality_agent.domain.models import (
    ArtifactLocation,
    CanonicalEndpoint,
    DeclaredContractCatalog,
    GeneratedArtifact,
    PostmanCollectionDocument,
)
from api_quality_agent.domain.services import (
    ApiAnalysisEngine,
    CanonicalEndpointNormalizer,
    ContractEndpointMatcher,
    DiffEngine,
    ExcelSchemaProvider,
    FallbackSchemaProvider,
    InferenceSchemaProvider,
    ManagedBlockMerger,
    SchemaInferenceEngine,
    TestStrategyEngine,
)
from api_quality_agent.generators import PostmanTestGenerator
from api_quality_agent.parsers import ExcelContractParser
from api_quality_agent.ports.outbound import ArtifactRepository, CollectionRepository

# R2-07/R2-09: compõe tudo que já existe (parser/matcher/providers das
# etapas anteriores) pra oferecer `generate --contract-file`, sem duplicar a
# lógica de geração/artefatos já testada em GenerateCollectionTestsUseCase e
# GenerateTestsFromDocumentUseCase — este use case só monta um
# AgentOrchestrator "ciente de contrato" (schema declarado com fallback pra
# inferência) e delega pra eles. Depois da geração, roda o matcher mais uma
# vez sobre TODAS as requests do documento (chamada extra, stateless e
# barata) só pra montar e persistir o relatório de correspondência — o
# AgentOrchestrator continua vendo requests uma de cada vez, sem mudança.
#
# get_current_workspace_use_case/resolve_collection_use_case/collection_repository
# só são necessários para execute_online(); execute_offline() nunca os usa
# (mesmo padrão já usado em RunCollectionUseCase para o caminho
# local_collection_path).

_LOCAL_FILE_WORKSPACE_ID = "local"
_UNSAFE_SLUG_CHARS = re.compile(r"[^A-Za-z0-9_.-]+")


class GenerateTestsWithContractUseCase:
    def __init__(
        self,
        excel_contract_parser: ExcelContractParser,
        analysis_engine: ApiAnalysisEngine,
        schema_inference_engine: SchemaInferenceEngine,
        test_strategy_engine: TestStrategyEngine,
        test_generator: PostmanTestGenerator,
        managed_block_merger: ManagedBlockMerger,
        diff_engine: DiffEngine,
        artifact_repository: ArtifactRepository,
        *,
        get_current_workspace_use_case: GetCurrentWorkspaceUseCase | None = None,
        resolve_collection_use_case: ResolveCollectionUseCase | None = None,
        collection_repository: CollectionRepository | None = None,
        id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._excel_contract_parser = excel_contract_parser
        self._analysis_engine = analysis_engine
        self._schema_inference_engine = schema_inference_engine
        self._test_strategy_engine = test_strategy_engine
        self._test_generator = test_generator
        self._managed_block_merger = managed_block_merger
        self._diff_engine = diff_engine
        self._artifact_repository = artifact_repository
        self._get_current_workspace_use_case = get_current_workspace_use_case
        self._resolve_collection_use_case = resolve_collection_use_case
        self._collection_repository = collection_repository
        self._id_factory = id_factory
        self._clock = clock

    def execute_online(
        self,
        *,
        contract_file: str,
        collection_id: str | None = None,
        collection_name: str | None = None,
    ) -> CollectionGenerationResult:
        if (
            self._get_current_workspace_use_case is None
            or self._resolve_collection_use_case is None
            or self._collection_repository is None
        ):
            raise InputError(
                "Este use case foi montado apenas para geração local; informe "
                "um documento ou monte-o com as dependências de Workspace/Postman."
            )

        catalog = self._excel_contract_parser.parse(contract_file).catalog
        normalizer = CanonicalEndpointNormalizer()
        matcher = ContractEndpointMatcher(normalizer)

        delegate = GenerateCollectionTestsUseCase(
            self._get_current_workspace_use_case,
            self._resolve_collection_use_case,
            self._collection_repository,
            self._build_orchestrator(catalog, matcher, normalizer),
            self._artifact_repository,
            id_factory=self._id_factory,
            clock=self._clock,
        )
        result = delegate.execute(collection_id=collection_id, collection_name=collection_name)

        assert result.execution_context.workspace_id is not None
        assert result.execution_context.collection_id is not None
        match_locations = self._save_match_report(
            contract_file,
            catalog,
            matcher,
            normalizer,
            result,
            workspace_id=result.execution_context.workspace_id,
            collection_id=result.execution_context.collection_id,
        )
        return replace(result, artifact_locations=result.artifact_locations + match_locations)

    def execute_offline(
        self, *, contract_file: str, document: PostmanCollectionDocument
    ) -> CollectionGenerationResult:
        catalog = self._excel_contract_parser.parse(contract_file).catalog
        normalizer = CanonicalEndpointNormalizer()
        matcher = ContractEndpointMatcher(normalizer)

        delegate = GenerateTestsFromDocumentUseCase(
            self._build_orchestrator(catalog, matcher, normalizer),
            self._artifact_repository,
            id_factory=self._id_factory,
            clock=self._clock,
        )
        result = delegate.execute(document=document)

        match_locations = self._save_match_report(
            contract_file,
            catalog,
            matcher,
            normalizer,
            result,
            workspace_id=_LOCAL_FILE_WORKSPACE_ID,
            collection_id=_slugify(document.name),
        )
        return replace(result, artifact_locations=result.artifact_locations + match_locations)

    def _build_orchestrator(
        self,
        catalog: DeclaredContractCatalog,
        matcher: ContractEndpointMatcher,
        normalizer: CanonicalEndpointNormalizer,
    ) -> AgentOrchestrator:
        excel_provider = ExcelSchemaProvider(catalog=catalog, matcher=matcher, normalizer=normalizer)
        inference_provider = InferenceSchemaProvider(self._schema_inference_engine)
        schema_provider = FallbackSchemaProvider(excel_provider, inference_provider)

        return AgentOrchestrator(
            self._analysis_engine,
            schema_provider,
            self._test_strategy_engine,
            self._test_generator,
            self._managed_block_merger,
            self._diff_engine,
        )

    def _save_match_report(
        self,
        contract_file: str,
        catalog: DeclaredContractCatalog,
        matcher: ContractEndpointMatcher,
        normalizer: CanonicalEndpointNormalizer,
        result: CollectionGenerationResult,
        *,
        workspace_id: str,
        collection_id: str,
    ) -> tuple[ArtifactLocation, ...]:
        # Import local: reporting/__init__.py importa report_engine.py, que
        # depende de application.use_cases (CollectionUpdateResult) — um
        # import no topo deste módulo criaria um ciclo real na inicialização
        # do pacote. Em tempo de execução (quando este método roda) os dois
        # pacotes já estão totalmente carregados, então não há problema.
        from api_quality_agent.reporting import (
            build_contract_match_report,
            render_contract_match_report_html,
            render_contract_match_report_json,
        )

        # Segunda chamada ao ApiAnalysisEngine sobre o mesmo documento (o
        # AgentOrchestrator já fez a primeira, internamente) — é puro/sem
        # estado, então repetir aqui só pra montar o relatório não tem
        # efeito colateral nem risco de inconsistência.
        analyzed_requests = self._analysis_engine.analyze_collection_requests(result.original_document)

        endpoints: list[CanonicalEndpoint] = []
        for analyzed in analyzed_requests:
            try:
                endpoints.append(
                    normalizer.normalize_collection_request(
                        analyzed.raw_request.method, analyzed.raw_request.url
                    )
                )
            except InvalidPostmanCollectionError:
                continue  # request sem URL/método utilizável: não entra no relatório

        match_results = matcher.match_all(tuple(endpoints), catalog)
        report = build_contract_match_report(contract_file, match_results)

        json_artifact = GeneratedArtifact(
            category="contracts",
            relative_path="contract-match-report.json",
            content=render_contract_match_report_json(report),
        )
        html_artifact = GeneratedArtifact(
            category="contracts",
            relative_path="contract-match-report.html",
            content=render_contract_match_report_html(report),
        )
        return (
            self._artifact_repository.save(
                workspace_id=workspace_id,
                collection_id=collection_id,
                execution_id=result.execution_context.execution_id,
                artifact=json_artifact,
            ),
            self._artifact_repository.save(
                workspace_id=workspace_id,
                collection_id=collection_id,
                execution_id=result.execution_context.execution_id,
                artifact=html_artifact,
            ),
        )


def _slugify(value: str) -> str:
    sanitized = _UNSAFE_SLUG_CHARS.sub("_", value).strip("_")
    return sanitized or "collection"
