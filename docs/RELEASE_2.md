# Release 2 — Integração de Contratos Excel

Documento técnico de acompanhamento da Release 2 (R2): geração de testes de
contrato a partir de planilhas Excel, pareadas com requests reais de uma
Collection Postman existente. Complementa o SAD e o Adendo v1.1 fornecidos
pelo time (não versionados neste repositório) com o estado real de
implementação, decisões de escopo confirmadas e o checklist por fase.

## Decisões de escopo confirmadas

- **R2-00 (planejamento)**: arquitetura do SAD verificada contra o código
  real. Conclusão: factível, com um único componente central alterado
  (`AgentOrchestrator`, mudança aditiva) e todo o resto em componentes novos
  e isolados. Um gate bloqueia a implementação do `ContractEndpointMatcher`
  até validação com uma Collection real (taxa de correspondência, uso de
  variáveis de infraestrutura e prefixos fixos).
- **R2-00B (caminho feliz)**: a Release 2 usa **exclusivamente o schema da
  resposta HTTP 200**. Seções de resposta para outros status codes (400,
  401, 403, 404, 409, 422, 500...) são reconhecidas pelo parser (pra não
  quebrar em planilhas reais que as tenham), mas **nunca** convertidas em
  schema nem usadas na geração. Nenhuma lógica de seleção de schema por
  status recebido em runtime, nenhuma asserção condicional em
  `pm.response.code`. Suporte a múltiplos status por endpoint é evolução
  futura da arquitetura — decisão de escopo de produto, não débito técnico.

## Nova dependência de runtime

`openpyxl>=3.1` — adicionada ao `pyproject.toml` na R2-02 (primeira
dependência nova desde o `PyYAML`), junto com `types-openpyxl` como
dependência de desenvolvimento (stubs pro `mypy`).

## Checklist de implementação por fase

- [x] **Fase 1 — Modelos de domínio** (R2-01, concluída)
  - `DeclaredSchema`, `DeclaredParameter`, `DeclaredRequestContract`,
    `DeclaredResponseContract`, `DeclaredEndpointContract`,
    `DeclaredContractCatalog` — `src/api_quality_agent/domain/models/`.
  - Imutáveis (`@dataclass(frozen=True)`), sem dependência de `openpyxl` nem
    de tipos específicos do Postman (só reaproveita `ParameterLocation`,
    já existente e genérico).
  - `DeclaredResponseContract` carrega só o schema de sucesso, sem
    `status_code` nem dicionário por status — reflete a decisão R2-00B
    diretamente no modelo, não apenas na lógica de geração.
  - Testes: `tests/unit/test_declared_contract_models.py` (24 testes —
    construção válida, imutabilidade, cada invariante de validação).
  - `mypy src`: limpo (201 arquivos). `pytest`: 902 passed, 1 skipped.
- [x] **Fase 2 (parcial) — `ExcelContractParser`** (R2-02, concluída; sem
      Validator/Matcher/CLI, conforme escopo pedido)
  - `src/api_quality_agent/parsers/excel_contract_parser.py`: lê o arquivo
    `.xlsx` (`openpyxl`, somente leitura, sem macros), localiza `URI`/
    `Método` por rótulo (sem depender de coordenadas fixas), reconhece as
    seções Header/Path Param/Query Param/Body/Resposta-por-status-code
    (tolerante a acento/espaço/caixa), reconstrói a árvore de
    objeto/array a partir da coluna `Sequencial` (suporta sequencial
    inteiro e pontuado), e converte `Formato`+`Obrigatoriedade` em
    `DeclaredSchema`/`DeclaredParameter`.
  - Decisão do adendo v1.1 aplicada: array sempre vira lista de objetos —
    os filhos diretos compõem `items` mesmo quando há só um filho.
  - Decisão R2-00B aplicada: só a seção "Status code 200" alimenta
    `DeclaredResponseContract.schema`; outras seções de resposta (ex.: 400)
    são reconhecidas (não quebram a leitura) mas descartadas.
  - Sem Validator: uma aba sem `URI`/`Método` utilizável simplesmente não
    vira contrato (não é registrada como `INVALID_CONTRACT` — isso fica
    pra uma fase posterior).
  - `Tamanho`/`Regras (Domínio)` não são lidos (fora de escopo do MVP).
  - Testes: `tests/unit/test_excel_contract_parser.py` (11 testes —
    metadados, cada seção de requisição, árvore de resposta 200 completa,
    confirmação de que a seção 400 nunca vaza pro schema, aba sem
    metadados, múltiplas abas, array com um único filho).
  - `mypy src`: limpo (202 arquivos). `pytest`: 913 passed, 1 skipped.
- [x] **Fase 2 (restante) — `ExcelContractValidator`** (R2-03, concluída)
  - **Evolução de interface (não é débito técnico)**: `ExcelContractParser.parse()`
    passou a devolver `ExcelParseResult` (`raw_rows` + `catalog`) em vez de só
    o catálogo. Decisão consciente: como nada fora dos próprios testes da
    R2-02 consumia `parse()` ainda, corrigir a interface agora (em vez de
    manter dois métodos por "compatibilidade" com um consumidor que não
    existe) evita duplicação de API. Testes da R2-02 atualizados pra usar
    `result.catalog`.
  - `RawContractRow` (`src/api_quality_agent/parsers/excel_contract_parser.py`):
    preserva toda linha de dado observada (mesmo com problema — sequencial
    duplicado, órfã, tipo desconhecido), com `sheet`/`section`/`row_number`
    pra rastreabilidade (ASR-06 do SAD).
  - Normalização compartilhada extraída pra
    `parsers/excel_contract_normalization.py` (usada por parser e validador,
    sem duplicar lógica).
  - `ExcelContractValidator.validate(raw_rows, catalog) -> tuple[ContractValidationIssue, ...]`
    (`parsers/excel_contract_validator.py`) — não recebe nem importa nada de
    Collection/Postman. Verifica: sequencial inválido/duplicado; pai
    inexistente (filho órfão); tipo desconhecido; array sem filhos
    declarados; path param marcado como não-obrigatório; outras seções de
    resposta reconhecidas e ignoradas (transparência da decisão R2-00B);
    endpoints duplicados (mesmo método+path) no catálogo.
  - Testes: `tests/unit/test_excel_contract_validator.py` (10 testes) +
    1 teste novo em `test_excel_contract_parser.py` (seção 400 aparece nas
    `raw_rows`).
  - `mypy src`: limpo (204 arquivos). `pytest`: 924 passed, 1 skipped.
- [ ] **Gate (adendo v1.1, seção 5)** — validação com Collection real antes
      da Fase 3.
- [x] **Fase 3 (parcial) — `CanonicalEndpointNormalizer` + `ContractEndpointMatcher`**
      (R2-04, concluída; gate R2-04A validado com a Collection real Swagger
      Petstore — ver decisão abaixo)
  - **Gate R2-04A**: analisada uma Collection Postman real (5 endpoints,
    variável `{{baseUrl}}` em todas as requests, parâmetro `{{petId}}` em
    duas). Veredito: **ARQUITETURA VALIDADA**, com um refinamento de
    implementação (não uma mudança de arquitetura): canonizar sempre a
    partir de `url.path` (array), nunca de `url.raw` — isso exclui
    `{{baseUrl}}` da comparação de graça, porque ele vive em `url.host`,
    nunca em `url.path`. Risco residual registrado e **não tratado por
    decisão**: remoção de prefixo fixo de path (`/api`, `/v1` etc.) não foi
    exercitada pelo exemplo real — nenhuma heurística de prefixo foi
    implementada.
  - `domain/models/canonical_endpoint.py` (`CanonicalEndpoint`),
    `domain/models/match_status.py` (`MatchStatus`: MATCHED/NOT_FOUND/
    AMBIGUOUS), `domain/models/contract_match_result.py` (`ContractMatchResult`).
  - `domain/services/canonical_endpoint_normalizer.py`
    (`CanonicalEndpointNormalizer`): prioriza `url.path`; cai pra `url.raw`
    só se `url.path` ausente/vazio (extraindo o path e descartando protocolo/
    domínio/host/query); normaliza `{id}`/`:id`/`{{id}}` → `{param}` (nome
    do parâmetro não importa, só a posição); nunca resolve variável de
    infraestrutura nem acessa Excel. Reaproveita
    `InvalidPostmanCollectionError` já existente pra "Collection inválida"
    (não criou exceção nova).
  - `domain/services/contract_endpoint_matcher.py` (`ContractEndpointMatcher`):
    só compara `CanonicalEndpoint` (método+path) já prontos contra o
    catálogo — nunca interpreta URL, nunca analisa query string, nunca
    acessa Excel. `MATCHED`/`NOT_FOUND`/`AMBIGUOUS` (candidatos ambíguos
    nunca escolhidos automaticamente).
  - Testes: `tests/unit/test_canonical_endpoint_normalizer.py` (15 —
    incluindo os 5 exemplos de URLs equivalentes do prompt, todos produzindo
    `/users/{param}`) e `tests/unit/test_contract_endpoint_matcher.py`
    (7 — match, not-found, método diferencia path igual, ambíguo nunca
    escolhido, `match_all`, garantia de escopo via introspecção de
    assinatura).
  - `mypy src`: limpo (209 arquivos). `pytest`: 946 passed, 1 skipped.
  - **Ruff — não aplicável ao estado atual do projeto** (decisão registrada
    após confirmação explícita): Ruff não foi executado porque não está
    instalado nem configurado no projeto; essa ausência já era documentada
    no README como limitação conhecida antes desta etapa. `mypy` executado
    com sucesso; `pytest` executado com sucesso. Nenhuma dependência ou
    configuração de ferramental foi alterada nesta etapa — a configuração
    do Ruff (dependência, regras de lint, integração com o fluxo de
    qualidade) fica registrada como tarefa independente, a ser tratada
    separadamente.
  - Ainda falta desta fase: `InfrastructureVariableResolver` (resolução de
    `{{baseUrl}}`/prefixo fixo via `--collection-path-prefix`) — decisão
    explícita de deixar fora deste passo (ver R2-04).
- [x] **Fase 4 (parcial) — `SchemaProvider`** (R2-05, concluída; `AgentOrchestrator`
      **ainda não foi alterado**, conforme pedido)
  - `ports/outbound/schema_provider.py` (`SchemaProvider`, `Protocol`
    `runtime_checkable`, seguindo a mesma convenção das portas já
    existentes): `resolve(request: CollectionRequest) -> SchemaResolution`.
    Sem `status_code` no método — consistente com a decisão R2-00B (só
    schema de sucesso, sem lógica de seleção por status).
  - `domain/models/schema_resolution.py` (`SchemaResolution`): `schema:
    dict | None` + `warnings` (reaproveita `SchemaInferenceWarning`
    existente — nenhum tipo de warning novo).
  - `domain/services/excel_schema_provider.py` (`ExcelSchemaProvider`):
    normaliza a request via `CanonicalEndpointNormalizer`, casa com o
    catálogo via `ContractEndpointMatcher`; só devolve schema quando o
    resultado é `MATCHED` **e** o contrato tem `response.schema` declarado;
    `NOT_FOUND`/`AMBIGUOUS`/schema ausente/URL inválida → `schema=None`,
    nunca levanta exceção. Inclui o conversor `DeclaredSchema` → dict de
    JSON Schema (necessário pra alimentar o `TestStrategyEngine` mais
    adiante).
  - `domain/services/inference_schema_provider.py` (`InferenceSchemaProvider`):
    replica o comportamento já existente hoje em
    `AgentOrchestrator._infer_response_schema` (extrai e desserializa
    Examples salvos, chama `SchemaInferenceEngine`). Duplicação **temporária
    e consciente** — o método privado original continua no orchestrator até
    a próxima etapa fazer a substituição de verdade.
  - Testes: `tests/unit/test_schema_provider.py` (2 — conformidade com o
    Protocol), `tests/unit/test_excel_schema_provider.py` (7),
    `tests/unit/test_inference_schema_provider.py` (5).
  - `mypy src`: limpo (213 arquivos). `pytest`: 960 passed, 1 skipped.
  - Ferramental: Ruff não executado (não instalado/configurado no projeto —
    já documentado como limitação conhecida no README, tratamento fica pra
    tarefa independente futura). `mypy` e `pytest` executados com sucesso;
    nenhuma dependência ou configuração de ferramental foi alterada.
- [x] **Fase 4 (conclusão) — `AgentOrchestrator` passa a consumir `SchemaProvider`**
      (R2-06, concluída; **único arquivo de produção alterado**)
  - Constructor: `schema_inference_engine: SchemaInferenceEngine` virou
    `schema_provider: SchemaProvider | SchemaInferenceEngine`.
    **Retrocompatibilidade real, não só nominal**: se um `SchemaInferenceEngine`
    "cru" for passado (todo callsite hoje faz isso — grep confirmou 9
    arquivos, incluindo `bootstrap.py`, `tests/acceptance/conftest.py` e 6
    arquivos de teste unitário — todos posicionais, nenhum por keyword), o
    `AgentOrchestrator` o empacota automaticamente num `InferenceSchemaProvider`
    internamente. **Nenhum desses 9 arquivos precisou ser alterado.**
  - `_process_endpoint` passa a chamar `self._schema_provider.resolve(raw_request)`
    em vez de `self._infer_response_schema(raw_request)`; o método privado
    `_infer_response_schema` foi removido (lógica agora só existe, uma vez,
    dentro de `InferenceSchemaProvider`).
  - Testes novos (`tests/unit/test_agent_orchestrator_schema_provider.py`,
    4): confirmam que (1) passar um `SchemaInferenceEngine` cru continua
    funcionando; (2) passar `SchemaInferenceEngine()` cru e
    `InferenceSchemaProvider(SchemaInferenceEngine())` explícito produzem
    **o script idêntico**, byte a byte; (3) `ExcelSchemaProvider` de fato
    dirige a geração a partir do schema declarado, mesmo sem Example salvo
    com aquele corpo; (4) sem match no catálogo, gera sem erro (nunca
    quebra).
  - Todos os 4 testes de `test_agent_orchestrator.py` (já existentes,
    caracterizando o comportamento atual) continuam passando **sem
    nenhuma alteração** — são a prova de regressão zero.
  - `mypy src`: limpo (213 arquivos). `pytest`: 964 passed, 1 skipped.
  - Ruff: mesma situação registrada nas etapas anteriores (não
    instalado/configurado); só `mypy`/`pytest` executados; nenhuma
    dependência/configuração de ferramental alterada.
- [x] **Fase 6 — CLI `generate --contract-file`** (R2-07, concluída; só a
      camada de CLI/composição, nenhum domain service/porta novo)
  - Flag `--contract-file` em `generate`, combinável com a seleção normal
    (online) ou com `--file` (offline); rejeita combinação com
    `--openapi-file`. Sem `--contract-file`, comportamento idêntico ao de
    antes (nenhum teste existente precisou mudar).
  - `GenerateTestsWithContractUseCase` (`application/use_cases/`) — única
    peça de composição nova, necessária porque `AgentOrchestrator` só pode
    ser construído com `PostmanTestGenerator` (import proibido em arquivos
    de comando pela regra de arquitetura já existente) — então essa
    montagem precisa acontecer fora do arquivo de comando. Constrói um
    `AgentOrchestrator` "ciente de contrato" (schema declarado com fallback
    pra inferência, via `FallbackSchemaProvider` novo) e delega pra
    `GenerateCollectionTestsUseCase`/`GenerateTestsFromDocumentUseCase`
    já existentes, sem duplicar a lógica de geração/artefatos.
    `get_current_workspace_use_case`/`resolve_collection_use_case`/
    `collection_repository` são `| None` (só usados por `execute_online`),
    mesmo padrão já usado em `RunCollectionUseCase`.
  - `FallbackSchemaProvider` (`domain/services/`): tenta o schema declarado
    primeiro; sem match/sem schema, cai pra inferência — implementa a
    política padrão descrita no SAD sem lógica nova além de delegação.
  - `bootstrap.py`: `CliContext`/`OfflineCliContext` ganham
    `excel_contract_parser`/`generate_with_contract_use_case`.
  - Testes: `tests/unit/test_cli_generate_contract_file.py` (6 — geração
    com contrato sem API Key, sem chamada de rede, sem vazar API Key,
    rejeição de `--contract-file`+`--openapi-file`, comportamento inalterado
    sem a flag).
  - Testado manualmente ponta a ponta: `collection.json` real +
    `contrato.xlsx` real → script gerado a partir do schema declarado.
    Confirmei que a asserção gerada (só status code, sem os campos
    aninhados do schema) tem paridade exata com o que a inferência já
    produzia hoje pra um exemplo real com a mesma forma aninhada — não é
    regressão nem bug novo, é característica pré-existente do
    `TestStrategyEngine`.
  - `mypy src`: limpo (215 arquivos). `pytest`: 970 passed, 1 skipped.
  - Ruff: mesma situação já registrada (não instalado/configurado; nada de
    ferramental alterado).
  - **Limitação conhecida, não resolvida nesta etapa**: arquivo de contrato
    ausente/corrompido mapeia hoje pro código de saída 8 (erro inesperado),
    não 2 (entrada inválida) — `ExcelContractParser`/`openpyxl` não têm
    tratamento de exceção específico pra isso ainda. Não é uma quebra (a
    CLI já captura genericamente e nunca deixa vazar um traceback cru), só
    uma classificação de código de saída menos precisa do que o ideal.
- [ ] **Fase 4** — characterization tests do `AgentOrchestrator` atual,
      depois `SchemaProvider` (porta) + `InferenceSchemaProvider`/
      `DeclaredSchemaProvider` + mudança aditiva no `AgentOrchestrator`.
- [ ] **Fase 5** — `GenerateTestsWithContractUseCase` + `ContractMatchReportWriter`.
- [ ] **Fase 6** — CLI: `--contract-file` e `--strict-contract-match` em
      `generate` (online e `--file`).
- [ ] **Fase 7** — integração ponta a ponta, regressão completa,
      README/GUIA_DE_USO, limitações do MVP documentadas.
