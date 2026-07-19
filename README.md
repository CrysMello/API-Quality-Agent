# API Quality Agent

Agente de automação de qualidade para APIs, executado por linha de comando. Analisa contratos (JSON, OpenAPI/Swagger, Collections Postman), gera schemas e testes, e pode se conectar opcionalmente ao Postman para atualizar Collections de forma controlada.

A estrutura segue arquitetura hexagonal: o domínio (`domain/`) não depende de formatos externos (Postman, OpenAPI) nem de integrações — parsers e adapters ficam nas bordas. Consulte o Software Architecture Document (SAD) para detalhes de arquitetura, requisitos e roadmap.

## Estado atual

Já implementados (com testes automatizados — 841 testes, incluindo uma suíte de aceitação ponta a ponta em `tests/acceptance/`; mypy limpo):

- **CLI instalável**: `--help`, `--version`, `config show`, `doctor`, `version`, `workspace list`, `workspace select`, `list`, `generate`, `update`, `run` e `report`. Todos reutilizam os use cases já existentes (nenhuma regra de negócio nova na CLI): `workspace select`/`generate`/`update`/`run` aceitam seleção de Collection por ID, nome, índice ou interativamente (lógica compartilhada em `cli/collection_selection.py`), com Ctrl+C/EOF cancelando de forma limpa em qualquer prompt (tratamento centralizado em `cli/interactive.py`). `generate --file <collection.json>` roda a análise/geração a partir de uma Collection exportada localmente, sem `POSTMAN_API_KEY` e sem nenhuma chamada de rede (`GenerateTestsFromDocumentUseCase`, modo `ExecutionMode.OFFLINE`). `update` gera os testes novamente a partir do estado *atual* da Collection no Postman e aplica a atualização remota (com preview, backup e confirmação padrão negativa) — reutiliza `GenerateCollectionTestsUseCase` + `UpdateCollectionUseCase` como já existiam, sem depender de artefatos de uma execução anterior do `generate`. `run` executa a Collection via Newman (`RunCollectionUseCase`), com o executável resolvido por `--newman-executable` > `NEWMAN_EXECUTABLE` > `"newman"`, mapeia o `ExecutionResult` para o código de saída (sucesso/falhas de teste/falha de infraestrutura são distinguidos, nunca por exceção), e persiste um resumo estruturado em `artifacts/run_<timestamp>/result.json` (schema `1.1`, aditivo sobre o `1.0` original — `PersistExecutionResultUseCase` + `JsonExecutionResultRepository`; nunca stdout/stderr brutos nem a Collection completa). `report` lê esse `result.json` (o mais recente por padrão, ou um `--input` específico) e gera um relatório HTML autocontido (`JsonExecutionResultReader` + `ReportEngine.render_execution_summary_html()` + `HtmlReportWriter`) — nunca reexecuta o Newman nem acessa o Postman; o código de saída representa se o relatório foi gerado, não se os testes passaram. Snapshots de contrato já existem e são testados na camada de aplicação, mas ainda não têm comando de CLI dedicado — ver limitações.
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
- **Report Engine** (`reporting/`): monta um relatório estruturado a partir dos resultados já produzidos pelas etapas anteriores, com dois pontos de entrada — `generate()` (fluxo completo: execução, Workspace/Collection, endpoints, avisos, diff, atualização, execução do Newman, artefatos) e `generate_from_execution_summary()` (a partir de um `ExecutionResultRecord` lido de um `result.json` persistido pelo `run`, sem etapa de geração — seções de endpoints/diff/update ficam semanticamente vazias, nunca inventadas). Serialização em JSON (schema de topo estável), HTML genérico (`render_report_html`, com escaping) e um HTML dedicado ao relatório de execução (`render_execution_report_html`, com cards, barra de progresso e banner PASSED/FAILED/INFRASTRUCTURE FAILURE — texto sempre visível, nunca só cor) — nunca inclui corpo de requisição/resposta, headers ou blocos de autenticação brutos.
- **Snapshots de contrato** (`ContractSnapshot` + `ContractComparisonEngine`): persistem uma representação puramente estrutural (schema, status codes, content types — nunca valores reais) por Workspace/Collection/método/endpoint, e comparam duas versões de forma determinística (campo adicionado/removido, mudança de tipo/`required`/enum, status code, content type). Atualizar um baseline existente exige `overwrite=True` explícito.
- **Testes de aceitação ponta a ponta** (`tests/acceptance/`): validam os fluxos completos do SAD compondo os componentes reais acima (sem mocks internos — só um servidor Postman local simulado e um processo Newman simulado), incluindo alternância entre Collections, isolamento de artefatos e confirmação de que a atualização remota simulada nunca atinge uma Collection não selecionada. Matriz requisito×teste e limitações conhecidas do MVP em `tests/acceptance/README.md`.

Principais limitações atuais (detalhadas em `tests/acceptance/README.md`): não há comando de CLI para snapshots de contrato, já implementados e testados na camada de aplicação, mas hoje só acionáveis compondo as classes diretamente em Python; a geração de testes (schema → estratégia → script) só existe para Collections Postman, não para especificações OpenAPI (que param na etapa de análise); `generate --file` cobre só a geração local (`ExecutionMode.OFFLINE`) — `update`/`run` sempre exigem uma Collection real no Postman, não há um caminho offline para eles; `run` não aceita um Environment externo do Postman (`environment_path` sempre `None`); `report` só gera HTML (`--format html` é a única opção nesta versão — Markdown/PDF/CSV ficam para depois) e só mostra contagens agregadas de falha (o `result.json` nunca guardou o detalhamento por request/teste, então o relatório não inventa uma tabela que não existe); snapshots de contrato ainda não estão conectados a nenhum fluxo de geração/atualização; sem relatório de cobertura de código configurado no projeto; sem lint automatizado configurado (só `mypy`).

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

# Depois de revisar os arquivos gerados em artifacts/.../scripts/, aplica a
# atualização na Collection remota do Postman (mesma seleção por ID/nome/
# índice/interativa de generate)
api-quality-agent update --collection-id <id>
api-quality-agent update -n "Fake Store API Collection"
api-quality-agent update 2
api-quality-agent update
api-quality-agent update --collection-id <id> --yes

# Executa a Collection via Newman (mesma seleção por ID/nome/índice/interativa)
api-quality-agent run --collection-id <id>
api-quality-agent run -n "Fake Store API Collection"
api-quality-agent run 2
api-quality-agent run

# Configura o caminho do executável do Newman quando ele não está resolvível
# direto pelo PATH (comum no Windows — "newman" no PATH pode apontar para um
# .ps1 que o subprocess do Python não executa diretamente; use o .cmd)
api-quality-agent run -c <id> --newman-executable "C:\Users\voce\AppData\Roaming\npm\newman.cmd"
# ...ou, se preferir configurar uma vez por sessão do terminal:
# $env:NEWMAN_EXECUTABLE="C:\Users\voce\AppData\Roaming\npm\newman.cmd"

# Gera um relatório HTML a partir do result.json mais recente em artifacts/
# (não precisa de POSTMAN_API_KEY nem executa o Newman de novo)
api-quality-agent report

# ...ou de um result.json específico
api-quality-agent report --input artifacts/run_20260720_103512123456/result.json

# Escolhe onde salvar (diretório ou caminho de arquivo)
api-quality-agent report --output artifacts/reports
api-quality-agent report --output meu_relatorio.html

# Substitui um relatório já existente (por padrão, report nunca sobrescreve)
api-quality-agent report --overwrite
```

Em `workspace select`, `generate`, `update` e `run`, apenas uma forma de seleção pode ser usada por vez (ID, nome, índice ou, só em `generate`, `--file`); combiná-las é rejeitado antes de qualquer chamada de rede. Sem `--yes` (em `generate`/`update`), sempre pedem confirmação antes de agir; qualquer resposta que não seja um "sim" reconhecido (incluindo Ctrl+C ou EOF, em qualquer prompt) cancela a operação sem alterar nada, com código de saída 9. Em `generate`/`update`/`run`, a seleção de Collection é sempre temporária (nunca sobrescreve a seleção ativa); já `workspace select`, ao ser confirmado, persiste o novo Workspace em `~/.api-quality-agent/selection.json` — e se o Workspace escolhido for diferente do anterior, a Collection ativa é limpa (pertencia ao contexto anterior).

`run` não pede confirmação (não é uma operação destrutiva) e nunca lança exceção para representar falha de teste ou de infraestrutura do Newman — ele sempre inspeciona o `ExecutionResult` devolvido por `RunCollectionUseCase` e mapeia para um código de saída: `0` (sucesso completo), `1` (Newman executou, mas houve falhas de assertion) ou `6` (falha de infraestrutura — executável não encontrado, timeout, Collection inválida; nesse caso nada é persistido, já que não há resumo real a salvar). O executável do Newman é resolvido nesta ordem: flag `--newman-executable` → variável de ambiente `NEWMAN_EXECUTABLE` → `"newman"` (padrão, via PATH). Nesta primeira versão, `run` não aceita um Environment externo do Postman.

Ao final de uma execução com sucesso ou com falhas de teste, `run` grava um resumo estruturado em `artifacts/run_<timestamp>/result.json` e mostra o caminho:

```
Result saved to:
  artifacts/run_20260720_103512123456/result.json
```

O JSON só tem dados já expostos pelo domínio — nunca stdout/stderr brutos do Newman, nunca a Collection completa, nunca segredos:

```json
{
  "execution": {"started_at": "...", "finished_at": "...", "duration_seconds": 34.1},
  "collection": {"id": "...", "name": "PetStore"},
  "summary": {"requests": 28, "assertions": 312, "passed": 309, "failed": 3},
  "success": false,
  "infrastructure_failure": null
}
```

Se a gravação falhar (ex.: disco cheio), isso nunca muda o resultado da execução dos testes — só imprime um aviso à parte; o código de saída continua refletindo se os testes passaram ou não.

**`report` nunca executa o Newman de novo nem acessa o Postman — ele só lê um `result.json` já persistido pelo `run`.** Fluxo completo:

```
api-quality-agent run     →  artifacts/run_<timestamp>/result.json
                           ↓
api-quality-agent report  →  artifacts/run_<timestamp>/report.html
```

Sem `--input`, usa o `result.json` mais recente encontrado em `artifacts/**/result.json` (por data de modificação) e avisa qual escolheu ("Using latest execution result: ..."). Sem `--output`, o relatório fica ao lado do `result.json` de origem; `--output` aceita um diretório (nome do arquivo vira `report_<timestamp>.html`, reaproveitando o timestamp do próprio `result.json`) ou um caminho de arquivo completo. Por padrão `report` nunca sobrescreve um relatório existente — precisa de `--overwrite` explícito.

**O código de saída de `report` representa se o relatório foi gerado, não se os testes passaram.** Um `result.json` com testes falhos (`success: false`) ainda gera um relatório com exit code `0` — o status real (`PASSED`/`FAILED`/`INFRASTRUCTURE FAILURE`) aparece dentro do relatório, nunca no exit code. Únicas exceções: entrada inválida (arquivo inexistente, JSON corrompido, schema não suportado) usa os códigos de validação já existentes, e Ctrl+C sempre cancela com código 9.

O `result.json` schema `1.0` (sem `workspace`/`schema_version`) continua legível — `report` mostra "N/A" no lugar do Workspace nesse caso, em vez de falhar.

`generate --file` roda só a análise/geração local (sem `update` remoto — não há Collection do Postman pra atualizar); os artefatos são salvos em `artifacts/local/<nome-da-collection>/<execução>/`, junto com os demais. Como o export pode conter tokens/headers salvos nos requests, evite versionar o arquivo — a pasta `local/` já é gitignored e serve bem pra isso.

**`generate` nunca altera a Collection remota — só `update` faz isso.** O fluxo recomendado é:

1. `api-quality-agent generate -c <collection-id>` — gera os scripts em `artifacts/.../scripts/` para revisão local; nada muda no Postman.
2. Revise os arquivos `.js` gerados.
3. `api-quality-agent update -c <collection-id>` — **gera os testes de novo**, a partir do estado *atual* da Collection no Postman (não lê os arquivos gerados no passo 1), mostra um preview (requests analisadas/alteradas/sem alteração, testes gerados, avisos), pede confirmação (padrão **negativo** — Enter vazio cancela, diferente de `generate`/`workspace select`), cria um backup local antes do upload e só então atualiza a Collection remota. Se a Collection tiver mudado entre os passos 1 e 3, o resultado do `update` reflete o estado novo — o preview do passo 1 pode não corresponder mais exatamente ao que será aplicado.

Os scripts de exemplo antigos em `local/` (ex.: `select_collection_and_generate.py`, com `COLLECTION_ID` editado manualmente no código) não são mais necessários — `api-quality-agent workspace select` + `generate` + `update` os substituem.

### Fluxos ainda sem comando de CLI (disponíveis via Python)

O relatório completo do pipeline de geração (`ReportEngine.generate()`, com endpoints/diff/atualização/execução do Newman — diferente do relatório de execução isolado que `report` já expõe) e snapshots de contrato já estão implementados e testados (ver "Estado atual"), mas hoje só são acionáveis compondo as classes diretamente em Python — não há comando de CLI para eles. Exemplo mínimo (selecionar Workspace/Collection e gerar testes — equivalente ao que `workspace select` + `generate` já fazem pela CLI):

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
