"""Garante que a camada CLI permaneça uma casca fina: os comandos só podem
compor use cases já existentes (via cli.bootstrap), nunca reimplementar
regras de negócio nem falar diretamente com adapters (HTTP do Postman,
Newman, backup, report engine).
"""

import ast
from pathlib import Path

COMMANDS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "src"
    / "api_quality_agent"
    / "cli"
    / "commands"
)

_FORBIDDEN_PREFIXES = (
    "api_quality_agent.adapters",
    "api_quality_agent.generators",
    "api_quality_agent.reporting",
)


def _imported_module_names(source_path: Path) -> set[str]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _command_files() -> list[Path]:
    return sorted(p for p in COMMANDS_DIR.glob("*.py") if p.name != "__init__.py")


def test_command_modules_never_import_adapters_generators_or_reporting_directly():
    for path in _command_files():
        imports = _imported_module_names(path)
        offending = {
            module
            for module in imports
            if any(module.startswith(prefix) for prefix in _FORBIDDEN_PREFIXES)
        }
        assert not offending, f"{path.name} importa diretamente: {offending}"


def test_command_modules_only_reach_postman_through_bootstrap():
    for path in _command_files():
        imports = _imported_module_names(path)
        assert "api_quality_agent.adapters.postman" not in imports
        assert all(not module.startswith("postman") for module in imports)


def test_bootstrap_is_the_only_place_wiring_adapters_for_the_cli():
    bootstrap_path = COMMANDS_DIR.parent / "bootstrap.py"
    imports = _imported_module_names(bootstrap_path)
    assert any(module.startswith("api_quality_agent.adapters") for module in imports)
