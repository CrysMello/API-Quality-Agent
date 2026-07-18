from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizationContext:
    # Indica se algum ancestral (pasta ou Collection) já declara autenticação
    # explícita, permitindo diferenciar AuthSource.INHERITED de AuthSource.NONE
    # quando a request não define "auth". None significa "desconhecido": o
    # chamador não resolveu a cadeia de herança (comportamento aceito nesta
    # etapa, gera aviso em vez de suposição).
    parent_has_explicit_auth: bool | None = None
