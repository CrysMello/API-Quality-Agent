# API Quality Agent

Agente de automação de qualidade para APIs, executado por linha de comando. Analisa contratos (JSON, OpenAPI/Swagger, Collections Postman), gera schemas e testes, e pode se conectar opcionalmente ao Postman para atualizar Collections de forma controlada.

A estrutura segue arquitetura hexagonal: o domínio (`domain/`) não depende de formatos externos (Postman, OpenAPI) nem de integrações — parsers e adapters ficam nas bordas. Consulte o Software Architecture Document (SAD) para detalhes de arquitetura, requisitos e roadmap.

## Estado atual

Já implementados (com testes automatizados):

- **CLI base**: `--help`, `--version`, `config show`, `doctor`.
- **Entrada**: `InputResolver` (arquivo/stdin/conteúdo direto) e `JsonDocumentParser`.
- **Parsers de contrato**: OpenAPI 3.x / Swagger 2.0 (JSON ou YAML, com resolução de `$ref` interno) e Collection Postman (preserva scripts, pastas aninhadas e itens desconhecidos).
- **Normalização Postman**: `auth`/`body`/`url` convertidos em modelos tipados (`NormalizedAuth`, `NormalizedBody`, `NormalizedUrl`), sem expor segredos.
- **API Analysis Engine**: relaciona endpoints, parâmetros, autenticação e dependências prováveis entre requests (sempre com evidência, nunca por suposição).
- **Schema Inference Engine**: gera JSON Schema determinístico a partir de exemplos, com políticas conservadoras (`required` só com evidência, sem inferir formatos por nome de campo).
- **Test Strategy Engine**: converte a análise em uma estratégia de testes estruturada (asserções, extrações de variável, cenários negativos), cada decisão com origem rastreável.
- **Postman Test Generator**: converte a estratégia em JavaScript comentado para o campo *Tests* do Postman, com resumo legível em português e warnings de inferências incertas.

Ainda não implementados: integração real com a API do Postman (`postman connect`, Workspaces/Collections remotas), execução via Newman, atualização controlada de Collections (Managed Block Merger) e relatórios (Report Engine).

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
