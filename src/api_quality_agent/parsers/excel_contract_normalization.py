import re
import unicodedata
from typing import Any

# Funções de normalização compartilhadas entre ExcelContractParser e
# ExcelContractValidator — nenhuma delas depende de openpyxl nem de tipos de
# domínio; operam só sobre valores de célula já extraídos.

TYPE_MAP: dict[str, str] = {
    "alfanumerico": "string",
    "texto": "string",
    "numerico": "number",
    "inteiro": "integer",
    "booleano": "boolean",
    "data": "string",
    "datahora": "string",
    "data e hora": "string",
    "objeto": "object",
    "arraylist": "array",
    "lista": "array",
}


def normalize_label(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().casefold()
    without_accents = "".join(
        char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", without_accents).strip()


def map_declared_type(raw_formato: Any) -> str | None:
    return TYPE_MAP.get(normalize_label(raw_formato))


def normalize_sequencial(value: Any) -> tuple[int, ...] | None:
    if isinstance(value, (int, float)):
        return (int(value),)
    text = str(value).strip()
    if not text:
        return None
    try:
        return tuple(int(part) for part in text.split("."))
    except ValueError:
        return None
