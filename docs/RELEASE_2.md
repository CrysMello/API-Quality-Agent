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

## Nova dependência de runtime (pendente de confirmação)

`openpyxl` — necessária para o `ExcelContractParser` (Fase 2). Ainda não
adicionada ao `pyproject.toml`; será a primeira dependência nova desde o
`PyYAML`.

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
- [ ] **Fase 2** — `ExcelContractParser` + `ExcelContractValidator` +
      fixture anonimizada baseada na planilha modelo. Requer confirmação
      para adicionar `openpyxl`.
- [ ] **Gate (adendo v1.1, seção 5)** — validação com Collection real antes
      da Fase 3.
- [ ] **Fase 3** — `CanonicalEndpointNormalizer` + `InfrastructureVariableResolver`
      + `ContractEndpointMatcher`.
- [ ] **Fase 4** — characterization tests do `AgentOrchestrator` atual,
      depois `SchemaProvider` (porta) + `InferenceSchemaProvider`/
      `DeclaredSchemaProvider` + mudança aditiva no `AgentOrchestrator`.
- [ ] **Fase 5** — `GenerateTestsWithContractUseCase` + `ContractMatchReportWriter`.
- [ ] **Fase 6** — CLI: `--contract-file` e `--strict-contract-match` em
      `generate` (online e `--file`).
- [ ] **Fase 7** — integração ponta a ponta, regressão completa,
      README/GUIA_DE_USO, limitações do MVP documentadas.
