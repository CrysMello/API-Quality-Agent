# Testes de aceitação — consolidação do MVP

Testes ponta a ponta que validam os fluxos definidos no SAD compondo os
componentes reais já implementados (parsers, domain services, orquestrador,
use cases, adapters), sem mocks internos. Os únicos limites simulados são as
bordas externas do sistema:

- **Postman**: servidor HTTP real e local (`tests/postman_test_server.py`),
  nunca a API real — sem internet, sem conta ou API Key reais.
- **Newman**: processo Python real e controlado (`tests/fake_newman.py`),
  nunca o binário Newman de verdade.
- **Filesystem**: diretórios reais sob `tmp_path` (isolados por teste).

Nenhum componente de `src/` foi reescrito ou alterado para viabilizar estes
testes — a suíte inteira passou compondo apenas classes já existentes.

## Como rodar

```bash
pytest tests/acceptance -v
```

## Estrutura

- `conftest.py` — fixtures/dados compartilhados (fake API key, IDs de
  Workspace/Collection A e B) e `build_app(...)`, que monta a árvore de
  dependências real (mesma composição que um futuro wiring de CLI usaria).
- `fixtures/*.json` — Collection Postman e especificação OpenAPI mínimas,
  para os cenários 100% offline.
- `test_offline_mode.py`, `test_workspace_and_collection_selection.py`,
  `test_generation_and_isolation.py`, `test_update_and_approval.py`,
  `test_execution_and_reporting.py`, `test_cli_exit_codes.py`.

## Matriz requisito × teste

| # | Cenário | Teste |
|---|---|---|
| 1 | Modo offline com JSON | `test_offline_mode.py::test_scenario_01_offline_mode_with_local_collection_json` |
| 2 | Modo offline com OpenAPI | `test_offline_mode.py::test_scenario_02_offline_mode_with_openapi_spec` |
| 3 | Conexão Postman simulada | `test_workspace_and_collection_selection.py::test_scenario_03_simulated_postman_connection_lists_workspaces` |
| 4 | Seleção de Workspace | `test_workspace_and_collection_selection.py::test_scenario_04_select_workspace_persists_choice` |
| 5 | Listagem de várias Collections | `test_workspace_and_collection_selection.py::test_scenario_05_list_multiple_collections` |
| 6 | Seleção da Collection A | `test_workspace_and_collection_selection.py::test_scenario_06_select_collection_a` |
| 7 | Geração para Collection A | `test_generation_and_isolation.py::test_scenario_07_generate_tests_for_collection_a` |
| 8 | Alternância para Collection B | `test_workspace_and_collection_selection.py::test_scenario_08_switch_active_collection_to_b` |
| 9 | Geração para Collection B | `test_generation_and_isolation.py::test_scenario_09_generate_tests_for_collection_b` |
| 10 | Isolamento dos artefatos | `test_generation_and_isolation.py::test_scenario_10_artifacts_are_isolated_between_collections` |
| 11 | Uso temporário de A sem alterar B como ativa | `test_workspace_and_collection_selection.py::test_scenario_11_temporary_use_of_a_does_not_change_active_b` |
| 12 | Nome duplicado exigindo ID | `test_workspace_and_collection_selection.py::test_scenario_12_duplicate_collection_name_requires_id` |
| 13 | Preservação de script manual | `test_generation_and_isolation.py::test_scenario_13_manual_script_is_preserved_during_generation` |
| 14 | Diff e aprovação | `test_update_and_approval.py::test_scenario_14_diff_reflects_generation_and_is_approved` |
| 15 | Bloqueio sem aprovação | `test_update_and_approval.py::test_scenario_15_update_is_blocked_without_explicit_approval` |
| 16 | Atualização simulada só da Collection escolhida | `test_update_and_approval.py::test_scenario_16_simulated_update_only_reaches_selected_collection` |
| 17 | Execução Newman simulada | `test_execution_and_reporting.py::test_scenario_17_simulated_newman_execution` |
| 18 | Relatório | `test_execution_and_reporting.py::test_scenario_18_report_reflects_the_full_flow` |
| 19 | API Key ausente dos logs | `test_execution_and_reporting.py::test_scenario_19_api_key_never_appears_in_logs_or_artifacts` |
| 20 | Falha do Postman sem impedir modo offline | `test_offline_mode.py::test_scenario_20_postman_failure_does_not_block_offline_mode` |
| — | Códigos de saída da CLI (`cli/exit_codes.py`) para as exceções reais destes fluxos | `test_cli_exit_codes.py` (6 testes) |

Critérios de aceite cobertos explicitamente:
- **Alternância entre Collections comprovada**: cenários 6, 8 e 11 (seleciona
  A, alterna para B, usa A temporariamente sem alterar B como ativa).
- **Atualização remota simulada nunca atinge Collection não selecionada**:
  cenário 16 configura a rota `PUT` apenas para a Collection A no servidor
  de teste e verifica que nenhuma chamada `PUT` foi feita para a Collection B.

## Relatório de cobertura

Não gerado. `pytest-cov`/`coverage` não estão instalados nem configurados
neste projeto (`pyproject.toml` não os lista como dependência de
desenvolvimento) — conforme a regra deste prompt ("se a ferramenta já
estiver configurada"), nenhuma ferramenta nova foi adicionada para produzir
este relatório.

## Limitações restantes do MVP

Identificadas ao validar os fluxos ponta a ponta. Lista revisada — os itens
originais "geração de testes só existe para Collections Postman", "nenhum
comando de CLI existe" e "`ExecutionMode.OFFLINE` não é usado em produção"
foram resolvidos em etapas posteriores (`generate`/`update`/`run`/`report`/
`workspace` na CLI; `generate --file`/`generate --openapi-file`/`run --file`
usando `ExecutionMode.OFFLINE` de verdade) e foram removidos daqui.

1. **`ContractSnapshot`/`ContractComparisonEngine`** ainda não estão
   conectados a nenhum fluxo de geração ou atualização — permanecem como
   componentes isolados, sem uso automático. Além do comando de CLI, falta
   também a peça intermediária: não existe hoje nenhum código (produção ou
   teste) que construa um `ContractSnapshot` a partir de dados reais de
   análise (`EndpointAnalysis`/`SchemaInferenceResult`) — os testes existentes
   constroem o snapshot manualmente, com schema fictício.
2. **Sem relatório de cobertura de código configurado** no projeto (ver seção
   acima).
3. **Política de aprovação, timeout do Newman e política de backup/retenção**
   são hoje parâmetros programáticos dos use cases, sem exposição via
   flags de CLI.
