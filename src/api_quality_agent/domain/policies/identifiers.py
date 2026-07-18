from api_quality_agent.domain.exceptions import InputError


def ensure_non_empty_id(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{field_name} deve ser uma string não vazia.")
    return value
