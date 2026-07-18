import shutil
import subprocess

_PAIRS = {")": "(", "]": "[", "}": "{"}
_OPENING = frozenset(_PAIRS.values())
_CLOSING = frozenset(_PAIRS.keys())
_STRING_DELIMITERS = frozenset({"'", '"', "`"})


def is_valid_javascript_syntax(script: str) -> bool:
    node_path = shutil.which("node")
    if node_path is not None:
        result = _validate_with_node(node_path, script)
        if result is not None:
            return result
    return _validate_with_bracket_balance(script)


def _validate_with_node(node_path: str, script: str) -> bool | None:
    try:
        completed = subprocess.run(
            [node_path, "--check"],
            input=script,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.returncode == 0


def _validate_with_bracket_balance(script: str) -> bool:
    # Heurística de fallback (sem parser real): apenas confirma balanceamento
    # de chaves/parênteses/colchetes fora de strings e comentários. Usada
    # somente quando Node.js não está disponível no ambiente.
    stack: list[str] = []
    in_string: str | None = None
    in_line_comment = False
    in_block_comment = False

    index = 0
    length = len(script)
    while index < length:
        char = script[index]
        next_char = script[index + 1] if index + 1 < length else ""

        if in_line_comment:
            if char == "\n":
                in_line_comment = False
            index += 1
            continue

        if in_block_comment:
            if char == "*" and next_char == "/":
                in_block_comment = False
                index += 2
                continue
            index += 1
            continue

        if in_string is not None:
            if char == "\\":
                index += 2
                continue
            if char == in_string:
                in_string = None
            index += 1
            continue

        if char == "/" and next_char == "/":
            in_line_comment = True
            index += 2
            continue
        if char == "/" and next_char == "*":
            in_block_comment = True
            index += 2
            continue
        if char in _STRING_DELIMITERS:
            in_string = char
            index += 1
            continue

        if char in _OPENING:
            stack.append(char)
        elif char in _CLOSING:
            if not stack or stack[-1] != _PAIRS[char]:
                return False
            stack.pop()

        index += 1

    return not stack and in_string is None and not in_block_comment
