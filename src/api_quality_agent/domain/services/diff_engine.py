from typing import Any

from api_quality_agent.domain.exceptions import ApiQualityAgentError
from api_quality_agent.domain.models import (
    CollectionEvent,
    CollectionFolder,
    CollectionItem,
    CollectionRequest,
    DiffCategory,
    DiffChangeType,
    DiffEntry,
    DiffResult,
    DiffRiskLevel,
    ManagedBlock,
    PostmanCollectionDocument,
)
from api_quality_agent.domain.services.managed_block_parser import ManagedBlockParser
from api_quality_agent.shared import mask_secret


class DiffEngine:
    def __init__(self, block_parser: ManagedBlockParser | None = None) -> None:
        self._block_parser = block_parser or ManagedBlockParser()

    def compare(
        self,
        original: PostmanCollectionDocument,
        modified: PostmanCollectionDocument,
    ) -> DiffResult:
        entries: list[DiffEntry] = []

        original_requests = _flatten_requests(original.items)
        modified_requests = _flatten_requests(modified.items)

        self._compare_requests(original_requests, modified_requests, entries)
        self._compare_matched_request_scripts(original_requests, modified_requests, entries)
        self._compare_variables(original.variables, modified.variables, entries)

        return DiffResult(entries=tuple(entries))

    @staticmethod
    def _compare_requests(
        original_requests: dict[str, CollectionRequest],
        modified_requests: dict[str, CollectionRequest],
        entries: list[DiffEntry],
    ) -> None:
        for key, request in modified_requests.items():
            if key not in original_requests:
                label = request.name or key
                entries.append(
                    DiffEntry(
                        change_type=DiffChangeType.ADDED,
                        category=DiffCategory.REQUEST,
                        target=f"request:{label}",
                        risk=DiffRiskLevel.LOW,
                        description=f"Request '{label}' adicionado.",
                    )
                )

        for key, request in original_requests.items():
            if key not in modified_requests:
                label = request.name or key
                entries.append(
                    DiffEntry(
                        change_type=DiffChangeType.REMOVED,
                        category=DiffCategory.REQUEST,
                        target=f"request:{label}",
                        risk=DiffRiskLevel.HIGH,
                        description=f"Request '{label}' removido.",
                    )
                )

    def _compare_matched_request_scripts(
        self,
        original_requests: dict[str, CollectionRequest],
        modified_requests: dict[str, CollectionRequest],
        entries: list[DiffEntry],
    ) -> None:
        for key, modified_request in modified_requests.items():
            original_request = original_requests.get(key)
            if original_request is None:
                continue
            label = f"request:{modified_request.name or key}"
            self._compare_events(original_request.events, modified_request.events, label, entries)

    def _compare_events(
        self,
        original_events: tuple[CollectionEvent, ...],
        modified_events: tuple[CollectionEvent, ...],
        request_label: str,
        entries: list[DiffEntry],
    ) -> None:
        original_by_listen = {event.listen: event for event in original_events if event.listen}
        modified_by_listen = {event.listen: event for event in modified_events if event.listen}

        for listen, modified_event in modified_by_listen.items():
            original_event = original_by_listen.get(listen)
            script_target = f"{request_label} > script:{listen}"

            if original_event is None:
                entries.append(
                    DiffEntry(
                        change_type=DiffChangeType.ADDED,
                        category=DiffCategory.SCRIPT,
                        target=script_target,
                        risk=DiffRiskLevel.LOW,
                        description=f"Script '{listen}' adicionado em '{request_label}'.",
                    )
                )
                continue

            original_text = "\n".join(original_event.exec_lines)
            modified_text = "\n".join(modified_event.exec_lines)
            if original_text == modified_text:
                continue

            self._compare_script_content(
                original_text, modified_text, request_label, listen, entries
            )

        for listen in original_by_listen:
            if listen not in modified_by_listen:
                entries.append(
                    DiffEntry(
                        change_type=DiffChangeType.REMOVED,
                        category=DiffCategory.SCRIPT,
                        target=f"{request_label} > script:{listen}",
                        risk=DiffRiskLevel.HIGH,
                        description=f"Script '{listen}' removido de '{request_label}'.",
                    )
                )

    def _compare_script_content(
        self,
        original_text: str,
        modified_text: str,
        request_label: str,
        listen: str,
        entries: list[DiffEntry],
    ) -> None:
        original_blocks, original_remainder = self._extract_managed_blocks_safe(original_text)
        modified_blocks, modified_remainder = self._extract_managed_blocks_safe(modified_text)

        block_ids = list(dict.fromkeys((*original_blocks.keys(), *modified_blocks.keys())))
        for block_id in block_ids:
            original_block = original_blocks.get(block_id)
            modified_block = modified_blocks.get(block_id)
            target = f"{request_label} > bloco:{block_id}"

            if original_block is None and modified_block is not None:
                entries.append(
                    DiffEntry(
                        change_type=DiffChangeType.ADDED,
                        category=DiffCategory.MANAGED_BLOCK,
                        target=target,
                        risk=DiffRiskLevel.LOW,
                        description=(
                            f"Bloco gerenciado '{block_id}' adicionado em '{request_label}'."
                        ),
                    )
                )
            elif original_block is not None and modified_block is None:
                entries.append(
                    DiffEntry(
                        change_type=DiffChangeType.REMOVED,
                        category=DiffCategory.MANAGED_BLOCK,
                        target=target,
                        risk=DiffRiskLevel.HIGH,
                        description=(
                            f"Bloco gerenciado '{block_id}' removido de '{request_label}'."
                        ),
                    )
                )
            elif (
                original_block is not None
                and modified_block is not None
                and original_block.content != modified_block.content
            ):
                entries.append(
                    DiffEntry(
                        change_type=DiffChangeType.MODIFIED,
                        category=DiffCategory.MANAGED_BLOCK,
                        target=target,
                        risk=DiffRiskLevel.MEDIUM,
                        description=(
                            f"Bloco gerenciado '{block_id}' atualizado em '{request_label}'."
                        ),
                    )
                )

        if original_remainder != modified_remainder:
            entries.append(
                DiffEntry(
                    change_type=DiffChangeType.MODIFIED,
                    category=DiffCategory.SCRIPT,
                    target=f"{request_label} > script:{listen}",
                    risk=DiffRiskLevel.MEDIUM,
                    description=(
                        f"Código fora de blocos gerenciados no script '{listen}' foi alterado "
                        f"em '{request_label}'."
                    ),
                )
            )

    def _extract_managed_blocks_safe(
        self, script_text: str
    ) -> tuple[dict[str, ManagedBlock], str]:
        try:
            blocks = self._block_parser.parse(script_text)
        except ApiQualityAgentError:
            return {}, script_text

        blocks_by_id = {block.block_id: block for block in blocks}
        remainder_parts: list[str] = []
        cursor = 0
        for block in sorted(blocks, key=lambda b: b.block_start):
            remainder_parts.append(script_text[cursor : block.block_start])
            cursor = block.block_end
        remainder_parts.append(script_text[cursor:])

        return blocks_by_id, "".join(remainder_parts)

    @staticmethod
    def _compare_variables(
        original_variables: tuple[dict[str, Any], ...],
        modified_variables: tuple[dict[str, Any], ...],
        entries: list[DiffEntry],
    ) -> None:
        original_by_key = {
            variable["key"]: variable.get("value")
            for variable in original_variables
            if isinstance(variable.get("key"), str)
        }
        modified_by_key = {
            variable["key"]: variable.get("value")
            for variable in modified_variables
            if isinstance(variable.get("key"), str)
        }

        for key, modified_value in modified_by_key.items():
            if key not in original_by_key:
                entries.append(
                    DiffEntry(
                        change_type=DiffChangeType.ADDED,
                        category=DiffCategory.VARIABLE,
                        target=f"variable:{key}",
                        risk=DiffRiskLevel.LOW,
                        description=(
                            f"Variável '{key}' adicionada "
                            f"(valor: {_mask_variable_value(modified_value)})."
                        ),
                    )
                )
            elif original_by_key[key] != modified_value:
                entries.append(
                    DiffEntry(
                        change_type=DiffChangeType.MODIFIED,
                        category=DiffCategory.VARIABLE,
                        target=f"variable:{key}",
                        risk=DiffRiskLevel.MEDIUM,
                        description=(
                            f"Variável '{key}' modificada "
                            f"(novo valor: {_mask_variable_value(modified_value)})."
                        ),
                    )
                )

        for key in original_by_key:
            if key not in modified_by_key:
                entries.append(
                    DiffEntry(
                        change_type=DiffChangeType.REMOVED,
                        category=DiffCategory.VARIABLE,
                        target=f"variable:{key}",
                        risk=DiffRiskLevel.HIGH,
                        description=f"Variável '{key}' removida.",
                    )
                )


def _flatten_requests(items: tuple[CollectionItem, ...]) -> dict[str, CollectionRequest]:
    result: dict[str, CollectionRequest] = {}
    counter = 0

    def _walk(nodes: tuple[CollectionItem, ...]) -> None:
        nonlocal counter
        for node in nodes:
            if isinstance(node, CollectionFolder):
                _walk(node.items)
            elif isinstance(node, CollectionRequest):
                key = node.item_id or node.name or f"__unnamed_request_{counter}__"
                counter += 1
                result[key] = node

    _walk(items)
    return result


def _mask_variable_value(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return "<vazio>"
    return mask_secret(value)
