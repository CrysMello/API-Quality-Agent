from dataclasses import dataclass

from api_quality_agent.domain.models.declared_schema import DeclaredSchema


@dataclass(frozen=True)
class DeclaredResponseContract:
    # Contrato declarado da resposta de sucesso (caminho feliz) — decisão de
    # escopo da Release 2 (R2-00B): representa exclusivamente o schema HTTP
    # 200. Não carrega status_code nem qualquer outra seção de resposta da
    # planilha (400/404/500/etc.), que são reconhecidas pelo parser mas
    # descartadas — não fazem parte deste modelo.
    schema: DeclaredSchema | None = None
