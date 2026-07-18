# API Quality Agent

Agente de automação de qualidade para APIs, executado por linha de comando. Analisa contratos (JSON, OpenAPI/Swagger, Collections Postman), gera schemas e testes, e pode se conectar opcionalmente ao Postman para atualizar Collections de forma controlada.

A estrutura segue arquitetura hexagonal: o domínio (`domain/`) não depende de formatos externos (Postman, OpenAPI) nem de integrações — parsers e adapters ficam nas bordas. Consulte o Software Architecture Document (SAD) para detalhes de arquitetura, requisitos e roadmap.

## Estado atual

Já implementados (com testes automatizados — 407 testes, mypy limpo):

- **CLI base**: `--help`, `--version`, `config show`, `doctor`. Os fluxos de seleção de Workspace/Collection e de geração de testes abaixo já existem na camada de aplicação, mas ainda não foram expostos como comandos de CLI.
- **Entrada**: `InputResolver` (arquivo/stdin/conteúdo direto) e `JsonDocumentParser`.
- **Parsers de contrato**: OpenAPI 3.x / Swagger 2.0 (JSON ou YAML, com resolução de `$ref` interno) e Collection Postman (preserva scripts, pastas aninhadas e itens desconhecidos).
- **Normalização Postman**: `auth`/`body`/`url` convertidos em modelos tipados (`NormalizedAuth`, `NormalizedBody`, `NormalizedUrl`), sem expor segredos.
- **API Analysis Engine**: relaciona endpoints, parâmetros, autenticação e dependências prováveis entre requests (sempre com evidência, nunca por suposição); também expõe cada request bruta pareada com sua análise (`analyze_collection_requests`), usado pelo orquestrador de geração.
- **Schema Inference Engine**: gera JSON Schema determinístico a partir de exemplos, com políticas conservadoras (`required` só com evidência, sem inferir formatos por nome de campo).
- **Test Strategy Engine**: converte a análise em uma estratégia de testes estruturada (asserções, extrações de variável, cenários negativos), cada decisão com origem rastreável.
- **Postman Test Generator**: converte a estratégia em JavaScript comentado para o campo *Tests* do Postman, com resumo legível em português e warnings de inferências incertas.
- **Integração com a API do Postman**: `PostmanApiClient` (via `urllib`, sem dependências de runtime novas) e os repositórios `PostmanWorkspaceRepository`/`PostmanCollectionRepository`, testados contra um servidor HTTP local (sem mocks). Somente leitura (listagem/obtenção) até o momento — nenhuma chamada de atualização remota é feita.
- **Seleção de Workspace/Collection**: `CollectionSelectionService` (resolução por id/nome com precedência clara) e os use cases `SelectWorkspaceUseCase`/`SelectCollectionUseCase`/`ResolveCollectionUseCase`/`ClearWorkspaceUseCase`/`ClearCollectionUseCase`/`ListWorkspacesUseCase`/`ListCollectionsUseCase`. A seleção ativa é persistida localmente (`FileSelectionRepository`) guardando apenas `workspace_id`/`collection_id` — nunca API key ou nomes.
- **Managed Block Merger**: mescla blocos gerados (`// <api-quality-agent:block id="...">...`) preservando código manual ao redor, com detecção de blocos duplicados/não fechados/corrompidos.
- **Diff Engine** e **Approval Policy**: comparam duas versões de uma Collection (requests, scripts, blocos gerenciados, variáveis) e decidem se uma atualização pode prosseguir (toda remoção é risco alto; `dry_run` sempre bloqueia).
- **Orquestração de geração** (`GenerateCollectionTestsUseCase` + `AgentOrchestrator`): para a Collection selecionada, executa o pipeline completo — parsing, análise, schema, estratégia, geração de scripts, merge em memória e diff — sem alterar a Collection original nem atualizar remotamente. Uma falha em um request específico não aborta os demais (resultado parcial, com contexto registrado). Os artefatos (scripts gerados e diff) são salvos isolados por `workspace_id`/`collection_id`/`execution_id` via `LocalArtifactRepository`.

Ainda não implementados: comandos de CLI para seleção de Workspace/Collection e para o fluxo de geração; atualização remota efetiva de Collections no Postman (a `ApprovalPolicy`/`DiffEngine` já existem, mas o comando de aplicação ainda não foi conectado); execução via Newman; relatórios (Report Engine).

## Instalação local

Requer Python 3.12 ou superior.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Comandos de qualidade

```bash
# Executar testes
pytest

# Verificação de tipos
mypy src
```
