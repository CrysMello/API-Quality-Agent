# API Quality Agent

Agente de automação de qualidade para APIs, executado por linha de comando. Analisa contratos (JSON, OpenAPI/Swagger, Collections Postman), gera schemas e testes, e pode se conectar opcionalmente ao Postman para atualizar Collections de forma controlada.

A estrutura segue arquitetura hexagonal: o domínio (`domain/`) não depende de formatos externos (Postman, OpenAPI) nem de integrações — parsers e adapters ficam nas bordas. Consulte o Software Architecture Document (SAD) para detalhes de arquitetura, requisitos e roadmap.

## Estado atual

Já implementados (com testes automatizados — 689 testes, incluindo uma suíte de aceitação ponta a ponta em `tests/acceptance/`; mypy limpo):

- **CLI instalável**: `--help`, `--version`, `config show`, `doctor`, `version`, `workspace list`, `workspace select`, `list` e `generate`. Todos reutilizam os use cases já existentes (nenhuma regra de negócio nova na CLI): `workspace select`/`generate` aceitam seleção por ID, nome, índice ou interativamente, sempre com confirmação prévia (pulável via `--yes`). `generate --file <collection.json>` roda a análise/geração a partir de uma Collection exportada localmente, sem `POSTMAN_API_KEY` e sem nenhuma chamada de rede (`GenerateTestsFromDocumentUseCase`, modo `ExecutionMode.OFFLINE`). Atualização remota, execução via Newman, relatórios e snapshots de contrato já existem e são testados na camada de aplicação, mas ainda não têm comando de CLI dedicado — ver limitações.
- **Entrada**: `InputResolver` (arquivo/stdin/conteúdo direto) e `JsonDocumentParser`.
- **Parsers de contrato**: OpenAPI 3.x / Swagger 2.0 (JSON ou YAML, com resolução de `$ref` interno) e Collection Postman (preserva scripts, pastas aninhadas e itens desconhecidos). `PostmanCollectionSerializer` faz o caminho inverso (documento → JSON do Postman), usado na atualização remota e no backup.
- **Normalização Postman**: `auth`/`body`/`url` convertidos em modelos tipados (`NormalizedAuth`, `NormalizedBody`, `NormalizedUrl`), sem expor segredos.
- **API Analysis Engine**: relaciona endpoints, parâmetros, autenticação e dependências prováveis entre requests (sempre com evidência, nunca por suposição), tanto para Collections Postman quanto para especificações OpenAPI (`analyze`/`analyze_specification`); também expõe cada request bruta pareada com sua análise (`analyze_collection_requests`), usado pelo orquestrador de geração.
- **Schema Inference Engine**: gera JSON Schema determinístico a partir de exemplos, com políticas conservadoras (`required` só com evidência, sem inferir formatos por nome de campo).
- **Test Strategy Engine**: converte a análise em uma estratégia de testes estruturada (asserções, extrações de variável, cenários negativos), cada decisão com origem rastreável.
- **Postman Test Generator**: converte a estratégia em JavaScript comentado para o campo *Tests* do Postman, com resumo legível em português e warnings de inferências incertas.
- **Integração com a API do Postman**: `PostmanApiClient` (via `urllib`, sem dependências de runtime novas), com leitura (`PostmanWorkspaceRepository`/`PostmanCollectionRepository`) e atualização (`update`, HTTP PUT), testados contra um servidor HTTP local (sem mocks).
- **Seleção de Workspace/Collection**: `CollectionSelectionService` (resolução por id/nome com precedência clara) e os use cases `SelectWorkspaceUseCase`/`SelectCollectionUseCase`/`ResolveCollectionUseCase`/`ClearWorkspaceUseCase`/`ClearCollectionUseCase`/`ListWorkspacesUseCase`/`ListCollectionsUseCase`. A seleção ativa é persistida localmente (`FileSelectionRepository`) guardando apenas `workspace_id`/`collection_id` — nunca API key ou nomes. Seleções temporárias (override por id/nome numa chamada pontual) nunca alteram a seleção ativa persistida.
- **Managed Block Merger**: mescla blocos gerados (`// <api-quality-agent:block id="...">...`) preservando código manual ao redor, com detecção de blocos duplicados/não fechados/corrompidos.
- **Diff Engine** e **Approval Policy**: comparam duas versões de uma Collection (requests, scripts, blocos gerenciados, variáveis) e decidem se uma atualização pode prosseguir (toda remoção é risco alto; `dry_run` sempre bloqueia).
- **Orquestração de geração** (`GenerateCollectionTestsUseCase` + `AgentOrchestrator`): para a Collection selecionada, executa o pipeline completo — parsing, análise, schema, estratégia, geração de scripts, merge em memória e diff — sem alterar a Collection original nem atualizar remotamente. Uma falha em um request específico não aborta os demais (resultado parcial, com contexto registrado). Os artefatos (scripts gerados e diff) são salvos isolados por `workspace_id`/`collection_id`/`execution_id` via `LocalArtifactRepository`.
- **Atualização remota segura** (`UpdateCollectionUseCase`): aplica em memória o resultado já aprovado via diff, atualizando *somente* a Collection selecionada (nunca por nome, nunca todas). Backup local da versão original antes de qualquer chamada remota (`LocalBackupRepository`): escrita atômica, nome único com timestamp e hash SHA-256, verificação de integridade, permissões restritivas de melhor esforço, retenção configurável e proteção contra versionamento acidental (`.gitignore`). O resultado devolvido carrega apenas metadados seguros (nunca o documento, o backup ou a resposta completa da API).
- **Newman Adapter + `RunCollectionUseCase`**: executa a Collection selecionada (ou um artefato local já gerado) via `subprocess` (sem shell, com timeout configurável), separando estruturalmente falhas de teste de falhas de infraestrutura (executável ausente, timeout, Collection inválida, erro inesperado). Segredos do arquivo de Environment do Postman (`"type": "secret"`) são mascarados na saída antes de entrarem no resultado.
- **Report Engine** (`reporting/`): monta um relatório estruturado (execução, Workspace/Collection, endpoints, avisos, diff, atualização, execução do Newman, artefatos) a partir dos resultados já produzidos pelas etapas anteriores, com serialização JSON (schema de topo estável), HTML (com escaping) e resumo textual para CLI — nunca inclui corpo de requisição/resposta, headers ou blocos de autenticação brutos.
- **Snapshots de contrato** (`ContractSnapshot` + `ContractComparisonEngine`): persistem uma representação puramente estrutural (schema, status codes, content types — nunca valores reais) por Workspace/Collection/método/endpoint, e comparam duas versões de forma determinística (campo adicionado/removido, mudança de tipo/`required`/enum, status code, content type). Atualizar um baseline existente exige `overwrite=True` explícito.
- **Testes de aceitação ponta a ponta** (`tests/acceptance/`): validam os fluxos completos do SAD compondo os componentes reais acima (sem mocks internos — só um servidor Postman local simulado e um processo Newman simulado), incluindo alternância entre Collections, isolamento de artefatos e confirmação de que a atualização remota simulada nunca atinge uma Collection não selecionada. Matriz requisito×teste e limitações conhecidas do MVP em `tests/acceptance/README.md`.

Principais limitações atuais (detalhadas em `tests/acceptance/README.md`): não há comando de CLI para atualização remota, execução via Newman, relatórios ou snapshots de contrato, todos já implementados e testados na camada de aplicação, mas hoje só acionáveis compondo as classes diretamente em Python; a geração de testes (schema → estratégia → script) só existe para Collections Postman, não para especificações OpenAPI (que param na etapa de análise); `generate --file` cobre só a geração local (`ExecutionMode.OFFLINE`) — não há um caminho equivalente em modo offline para atualização remota/Newman/relatório, que continuam exigindo uma Collection real no Postman; snapshots de contrato ainda não estão conectados a nenhum fluxo de geração/atualização; sem relatório de cobertura de código configurado no projeto.

## Instalação local

Requer Python 3.12 ou superior.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Como usar

### Instalação e configuração

Depois de instalado (`pip install -e ".[dev]"`), o executável `api-quality-agent` fica disponível no ambiente (registrado via `[project.scripts]`). A API Key do Postman é lida da variável de ambiente `POSTMAN_API_KEY` — nunca de um arquivo, argumento de linha de comando ou de qualquer valor persistido em disco:

```bash
export POSTMAN_API_KEY="sua-chave-aqui"        # Windows (PowerShell): $env:POSTMAN_API_KEY = "sua-chave-aqui"
api-quality-agent config show                  # confirma que a chave está configurada (mascarada)
api-quality-agent doctor                       # verifica pré-requisitos locais
```

### Uso pela linha de comando

```bash
api-quality-agent --help
api-quality-agent --version
api-quality-agent version

# Lista os Workspaces disponíveis para a API Key configurada
api-quality-agent workspace list

# Seleciona o Workspace ativo, por ID, por nome, pelo índice mostrado por
# `workspace list`, ou interativamente (mesmas regras de generate, abaixo)
api-quality-agent workspace select --workspace-id <id>
api-quality-agent workspace select --workspace-name "Meu Workspace"
api-quality-agent workspace select 1
api-quality-agent workspace select

# Lista as Collections do Workspace ativo
api-quality-agent list

# Gera e aplica os testes em uma Collection específica, por ID...
api-quality-agent generate --collection-id 31333303-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# ...ou por nome (deve ser único no Workspace; se houver mais de uma Collection
# com esse nome, o comando lista os IDs e pede para usar --collection-id)...
api-quality-agent generate --collection-name "Fake Store API Collection"

# ...ou pelo índice mostrado por `list`...
api-quality-agent generate 2

# ...ou interativamente, escolhendo a partir da listagem exibida no terminal
api-quality-agent generate

# Pula a confirmação final (útil em scripts/automação)
api-quality-agent generate --collection-id <id> --yes

# Gera os testes a partir de uma Collection exportada localmente (Postman >
# Collection > Export), sem conectar à API do Postman e sem precisar de
# POSTMAN_API_KEY — útil quando você só tem o arquivo, ou quer gerar os
# scripts offline para colar manualmente depois
api-quality-agent generate --file local/collections/minha_collection_exportada.json
```

Em `workspace select` e `generate`, apenas uma forma de seleção pode ser usada por vez (ID, nome, índice ou `--file`); combiná-las é rejeitado antes de qualquer chamada de rede. Sem `--yes`, todos sempre pedem confirmação antes de persistir a seleção (ou gerar/aplicar os testes); qualquer resposta que não seja um "sim" reconhecido (incluindo Ctrl+C) cancela a operação sem alterar nada. Em `generate`, a seleção de Collection é sempre temporária (nunca sobrescreve a seleção ativa); já `workspace select`, ao ser confirmado, persiste o novo Workspace em `~/.api-quality-agent/selection.json` — e se o Workspace escolhido for diferente do anterior, a Collection ativa é limpa (pertencia ao contexto anterior).

`generate --file` roda só a análise/geração local (sem `update` remoto — não há Collection do Postman pra atualizar); os artefatos são salvos em `artifacts/local/<nome-da-collection>/<execução>/`, junto com os demais. Como o export pode conter tokens/headers salvos nos requests, evite versionar o arquivo — a pasta `local/` já é gitignored e serve bem pra isso.

Os scripts de exemplo antigos em `local/` (ex.: `select_collection_and_generate.py`, com `COLLECTION_ID` editado manualmente no código) não são mais necessários — `api-quality-agent workspace select` + `generate` os substituem.

### Fluxos ainda sem comando de CLI (disponíveis via Python)

Atualização remota, execução via Newman, relatórios e snapshots de contrato já estão implementados e testados (ver "Estado atual"), mas hoje só são acionáveis compondo as classes diretamente em Python — não há comando de CLI para eles. Exemplo mínimo (selecionar Workspace/Collection e gerar testes — equivalente ao que `workspace select` + `generate` já fazem pela CLI):

```python
import os

from api_quality_agent.adapters.config import FileSelectionRepository
from api_quality_agent.adapters.filesystem import LocalArtifactRepository
from api_quality_agent.adapters.postman import (
    PostmanApiClient,
    PostmanCollectionRepository,
    PostmanWorkspaceRepository,
)
from api_quality_agent.application.orchestration import AgentOrchestrator
from api_quality_agent.application.use_cases import (
    GenerateCollectionTestsUseCase,
    GetCurrentWorkspaceUseCase,
    ResolveCollectionUseCase,
    SelectCollectionUseCase,
    SelectWorkspaceUseCase,
)
from api_quality_agent.domain.services import (
    ApiAnalysisEngine,
    CollectionSelectionService,
    DiffEngine,
    ManagedBlockMerger,
    SchemaInferenceEngine,
    TestStrategyEngine,
)
from api_quality_agent.generators import PostmanTestGenerator

client = PostmanApiClient(os.environ["POSTMAN_API_KEY"])
workspace_repository = PostmanWorkspaceRepository(client)
collection_repository = PostmanCollectionRepository(client)
selection_repository = FileSelectionRepository()  # persiste em ~/.api-quality-agent/selection.json
selection_service = CollectionSelectionService(collection_repository)

SelectWorkspaceUseCase(workspace_repository, selection_repository).execute(workspace_name="Meu Workspace")
SelectCollectionUseCase(selection_service, selection_repository).execute(collection_name="Minha Collection")

orchestrator = AgentOrchestrator(
    ApiAnalysisEngine(), SchemaInferenceEngine(), TestStrategyEngine(),
    PostmanTestGenerator(), ManagedBlockMerger(), DiffEngine(),
)
generate = GenerateCollectionTestsUseCase(
    GetCurrentWorkspaceUseCase(selection_repository),
    ResolveCollectionUseCase(selection_service, collection_repository, selection_repository),
    collection_repository, orchestrator, LocalArtifactRepository(),
)
result = generate.execute()
print(f"{len(result.endpoint_outcomes)} endpoints processados; diff com mudanças: {result.diff.has_changes}")
```

A mesma composição, estendida com atualização remota (`UpdateCollectionUseCase`), execução via Newman (`RunCollectionUseCase` + `NewmanAdapter`) e relatório (`ReportEngine`), está em `tests/acceptance/conftest.py::build_app` — é a montagem de referência, validada pela suíte de aceitação. `tests/acceptance/README.md` documenta a jornada completa (seleção → geração → atualização → execução → relatório) passo a passo.

## Comandos de qualidade

```bash
# Executar testes
pytest

# Verificação de tipos
mypy src
```

## Author

Projeto idealizado, arquitetado e mantido por Crystiane Mello.

Este projeto foi desenvolvido utilizando uma abordagem de Human-directed AI development. Ferramentas de Inteligência Artificial foram utilizadas como apoio à análise, documentação e implementação, enquanto a concepção, as decisões de arquitetura, o direcionamento, a revisão, a validação e a manutenção permaneceram sob responsabilidade da autora.

- **Nome**: Crystiane Mello
- **Papéis**: Creator, Architect, Maintainer
- **Abordagem de desenvolvimento**: Human-directed AI development
- **GitHub**: [https://github.com/CrysMello](https://github.com/CrysMello)
- **LinkedIn**: [https://www.linkedin.com/in/crystianemello/](https://www.linkedin.com/in/crystianemello/)
