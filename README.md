# API Quality Agent

Agente de automação de qualidade para APIs, executado por linha de comando. Analisa contratos (JSON, OpenAPI/Swagger, Collections Postman), gera schemas e testes, e pode se conectar opcionalmente ao Postman para atualizar Collections de forma controlada.

Este repositório está em fase de fundação arquitetural: a estrutura segue arquitetura hexagonal (domínio independente de integrações externas), mas ainda não implementa regras de negócio, CLI funcional ou integrações.

Consulte o Software Architecture Document (SAD) para detalhes de arquitetura, requisitos e roadmap.

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
