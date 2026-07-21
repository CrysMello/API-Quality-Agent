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
- [ ] **Fase 2 (restante)** — `ExcelContractValidator` (consistência:
      sequencial duplicado, filho sem pai, tipo desconhecido, regra de aba
      candidata formal com `INVALID_CONTRACT`).
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
