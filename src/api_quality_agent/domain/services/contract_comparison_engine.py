from typing import Any

from api_quality_agent.domain.exceptions import InputError
from api_quality_agent.domain.models import (
    ChangeSeverity,
    ContractChange,
    ContractChangeType,
    ContractSnapshot,
)


class ContractComparisonEngine:
    def compare(
        self, baseline: ContractSnapshot, current: ContractSnapshot
    ) -> tuple[ContractChange, ...]:
        if baseline.key != current.key:
            raise InputError(
                "Não é possível comparar snapshots de endpoints/Collections diferentes "
                f"({baseline.key} vs {current.key}); as comparações são sempre isoladas por chave."
            )

        changes: list[ContractChange] = []
        changes.extend(_compare_status_codes(baseline.status_codes, current.status_codes))
        changes.extend(_compare_content_types(baseline.content_types, current.content_types))
        changes.extend(_compare_schema(baseline.schema, current.schema, path="$"))
        return tuple(changes)


def _compare_status_codes(old: tuple[str, ...], new: tuple[str, ...]) -> list[ContractChange]:
    # Conjuntos, não listas: ordem não gera mudança.
    if set(old) == set(new):
        return []
    return [
        ContractChange(
            change_type=ContractChangeType.STATUS_CODE_CHANGED,
            severity=ChangeSeverity.MEDIUM,
            field_path="$.status_codes",
            description=f"Status codes documentados alterados: {sorted(old)} -> {sorted(new)}.",
        )
    ]


def _compare_content_types(old: tuple[str, ...], new: tuple[str, ...]) -> list[ContractChange]:
    if set(old) == set(new):
        return []
    return [
        ContractChange(
            change_type=ContractChangeType.CONTENT_TYPE_CHANGED,
            severity=ChangeSeverity.MEDIUM,
            field_path="$.content_types",
            description=f"Content types documentados alterados: {sorted(old)} -> {sorted(new)}.",
        )
    ]


def _compare_schema(
    old_schema: dict[str, Any] | None, new_schema: dict[str, Any] | None, *, path: str
) -> list[ContractChange]:
    old = old_schema or {}
    new = new_schema or {}
    changes: list[ContractChange] = []

    old_type = _normalize_type(old.get("type"))
    new_type = _normalize_type(new.get("type"))
    if old_type is not None and new_type is not None and old_type != new_type:
        changes.append(
            ContractChange(
                change_type=ContractChangeType.TYPE_CHANGED,
                severity=ChangeSeverity.HIGH,
                field_path=path,
                description=f"Tipo alterado em '{path}': {old_type!r} -> {new_type!r}.",
            )
        )

    old_enum = _normalize_enum(old.get("enum"))
    new_enum = _normalize_enum(new.get("enum"))
    if (old_enum is not None or new_enum is not None) and old_enum != new_enum:
        changes.append(
            ContractChange(
                change_type=ContractChangeType.ENUM_CHANGED,
                severity=ChangeSeverity.MEDIUM,
                field_path=path,
                description=f"Enum alterado em '{path}': {old_enum!r} -> {new_enum!r}.",
            )
        )

    changes.extend(_compare_properties(old, new, path=path))

    if "items" in old or "items" in new:
        changes.extend(
            _compare_schema(old.get("items"), new.get("items"), path=f"{path}[]")
        )

    return changes


def _compare_properties(
    old: dict[str, Any], new: dict[str, Any], *, path: str
) -> list[ContractChange]:
    changes: list[ContractChange] = []

    old_properties = _as_dict(old.get("properties"))
    new_properties = _as_dict(new.get("properties"))
    old_required = set(old.get("required") or [])
    new_required = set(new.get("required") or [])

    for key, child_schema in new_properties.items():
        child_path = f"{path}.{key}"
        if key not in old_properties:
            changes.append(
                ContractChange(
                    change_type=ContractChangeType.FIELD_ADDED,
                    severity=ChangeSeverity.LOW,
                    field_path=child_path,
                    description=f"Campo adicionado: '{child_path}'.",
                )
            )
            continue

        changes.extend(_compare_schema(old_properties[key], child_schema, path=child_path))

        was_required = key in old_required
        is_required = key in new_required
        if was_required != is_required:
            changes.append(
                ContractChange(
                    change_type=ContractChangeType.REQUIRED_CHANGED,
                    severity=ChangeSeverity.MEDIUM,
                    field_path=child_path,
                    description=(
                        f"Obrigatoriedade alterada em '{child_path}': "
                        f"required={was_required} -> required={is_required}."
                    ),
                )
            )

    for key in old_properties:
        if key not in new_properties:
            child_path = f"{path}.{key}"
            changes.append(
                ContractChange(
                    change_type=ContractChangeType.FIELD_REMOVED,
                    severity=ChangeSeverity.HIGH,
                    field_path=child_path,
                    description=f"Campo removido: '{child_path}'.",
                )
            )

    return changes


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_type(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, list):
        return tuple(sorted(value))
    return value


def _normalize_enum(value: Any) -> tuple[Any, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        return (value,)
    try:
        return tuple(sorted(value))
    except TypeError:
        # valores não ordenáveis entre si (ex.: mistura de tipos): preserva
        # a ordem original em vez de falhar a comparação.
        return tuple(value)
