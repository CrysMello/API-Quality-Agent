from collections.abc import Callable
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
from api_quality_agent.domain.exceptions import InputError
from api_quality_agent.domain.models import PostmanCollectionDocument
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

# R2-07: compõe tudo que já existe (parser/matcher/providers das etapas
# anteriores) pra oferecer `generate --contract-file`, sem duplicar a lógica
# de geração/artefatos já testada em GenerateCollectionTestsUseCase e
# GenerateTestsFromDocumentUseCase — este use case só monta um
# AgentOrchestrator "ciente de contrato" (schema declarado com fallback pra
# inferência) e delega pra eles.
#
# get_current_workspace_use_case/resolve_collection_use_case/collection_repository
# só são necessários para execute_online(); execute_offline() nunca os usa
# (mesmo padrão já usado em RunCollectionUseCase para o caminho
# local_collection_path).


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

        delegate = GenerateCollectionTestsUseCase(
            self._get_current_workspace_use_case,
            self._resolve_collection_use_case,
            self._collection_repository,
            self._build_orchestrator(contract_file),
            self._artifact_repository,
            id_factory=self._id_factory,
            clock=self._clock,
        )
        return delegate.execute(collection_id=collection_id, collection_name=collection_name)

    def execute_offline(
        self, *, contract_file: str, document: PostmanCollectionDocument
    ) -> CollectionGenerationResult:
        delegate = GenerateTestsFromDocumentUseCase(
            self._build_orchestrator(contract_file),
            self._artifact_repository,
            id_factory=self._id_factory,
            clock=self._clock,
        )
        return delegate.execute(document=document)

    def _build_orchestrator(self, contract_file: str) -> AgentOrchestrator:
        catalog = self._excel_contract_parser.parse(contract_file).catalog
        normalizer = CanonicalEndpointNormalizer()
        matcher = ContractEndpointMatcher(normalizer)
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
