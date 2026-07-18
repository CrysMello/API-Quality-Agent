from typing import Any

from api_quality_agent.domain.exceptions import UnresolvedReferenceError


class ReferenceResolver:
    def __init__(self, root_document: dict[str, Any]) -> None:
        self._root_document = root_document
        self._warnings: list[str] = []

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(self._warnings)

    def resolve(self, node: Any) -> Any:
        return self._resolve(node, resolving=frozenset())

    def _resolve(self, node: Any, *, resolving: frozenset[str]) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str):
                return self._resolve_ref(ref, resolving=resolving)
            return {key: self._resolve(value, resolving=resolving) for key, value in node.items()}
        if isinstance(node, list):
            return [self._resolve(item, resolving=resolving) for item in node]
        return node

    def _resolve_ref(self, ref: str, *, resolving: frozenset[str]) -> Any:
        if not ref.startswith("#/"):
            self._warnings.append(f"Referência externa não resolvida: {ref}")
            return {"$ref": ref}

        # Referência circular: preserva o ponteiro sem expandir mais fundo,
        # evitando recursão infinita em estruturas de dados recursivas.
        if ref in resolving:
            return {"$ref": ref}

        target = self._navigate(ref)
        if target is None:
            raise UnresolvedReferenceError(f"Referência interna não encontrada: {ref}")

        return self._resolve(target, resolving=resolving | {ref})

    def _navigate(self, ref: str) -> Any:
        pointer = ref[2:]
        if pointer == "":
            return self._root_document

        current: Any = self._root_document
        for raw_segment in pointer.split("/"):
            segment = _unescape_json_pointer_segment(raw_segment)
            if isinstance(current, dict):
                if segment not in current:
                    return None
                current = current[segment]
            elif isinstance(current, list):
                try:
                    index = int(segment)
                except ValueError:
                    return None
                if index < 0 or index >= len(current):
                    return None
                current = current[index]
            else:
                return None
        return current


def _unescape_json_pointer_segment(segment: str) -> str:
    return segment.replace("~1", "/").replace("~0", "~")
