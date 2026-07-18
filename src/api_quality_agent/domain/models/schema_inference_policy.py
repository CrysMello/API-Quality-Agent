from dataclasses import dataclass

DEFAULT_SCHEMA_DIALECT = "http://json-schema.org/draft-07/schema#"


@dataclass(frozen=True)
class SchemaInferencePolicy:
    # Desligado por padrão: string com aparência de data continua "string"
    # simples, salvo ativação explícita desta opção (regra de negócio).
    infer_date_format: bool = False
    schema_dialect: str = DEFAULT_SCHEMA_DIALECT
