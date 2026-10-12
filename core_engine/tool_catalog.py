"""@tool registry & provider bindings for the Novous core engine.

Registry-only catalog: does not define any tools directly. All tool definitions
are discovered dynamically from the tools/ directory.
"""

import importlib.util
import inspect
import json
from pathlib import Path
import sys
from typing import Callable

REGISTRY: dict[str, dict] = {}
LOAD_ERRORS: dict[str, str] = {}
REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
_LOADED_FILES: set[Path] = set()

PROVIDER_BINDINGS = {
    "core_engine": "core_engine.interface",
    "editor": "editor.interface",
    "workspace": "workspace.interface",
    "test_environment": "test_environment.interface",
    "codebuilder": "codebuilder.interface",
    "tools": "tools.interface",
}


def tool(name_or_func: str | Callable | None = None, provider: str = "core_engine"):
    """Decorator that registers a function as an invocable agent tool."""

    def decorator(func: Callable) -> Callable:
        tool_name = name_or_func if isinstance(name_or_func, str) else func.__name__
        if tool_name in REGISTRY and REGISTRY[tool_name]["function"] is not func:
            raise ValueError(
                f"Tool '{tool_name}' is already registered by provider '{REGISTRY[tool_name]['provider']}'."
            )
        doc = inspect.getdoc(func) or ""
        func.name = tool_name
        func.provider = provider
        REGISTRY[tool_name] = {
            "name": tool_name,
            "function": func,
            "provider": provider,
            "description": doc.splitlines() if doc else "",
            "signature": str(inspect.signature(func)),
        }
        return func

    if callable(name_or_func):
        func = name_or_func
        name_or_func = None
        return decorator(func)
    return decorator


def load_tools(reload: bool = False) -> None:
    """Auto-import every *.py in TOOLS_DIR except __init__.py, interface.py, _*.py."""
    if reload:
        REGISTRY.clear()
        LOAD_ERRORS.clear()
        _LOADED_FILES.clear()

    if not TOOLS_DIR.is_dir():
        return

    for path in sorted(TOOLS_DIR.glob("*.py")):
        if path.name in ("__init__.py", "interface.py") or path.name.startswith("_"):
            continue
        if not reload and path.resolve() in _LOADED_FILES:
            continue

        module_name = f"tools.{path.stem}"
        snapshot = dict(REGISTRY)
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Could not load spec for '{path.name}'.")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            _LOADED_FILES.add(path.resolve())
            LOAD_ERRORS.pop(path.name, None)
        except Exception as exc:
            LOAD_ERRORS[path.name] = str(exc)
            # Revert any tools registered by this failed module
            for k in list(REGISTRY.keys()):
                if k not in snapshot:
                    REGISTRY.pop(k, None)
            sys.modules.pop(module_name, None)


def list_tools() -> list[dict]:
    """Return catalog metadata for all registered tools."""
    load_tools()
    return [
        {
            "name": meta["name"],
            "provider": meta["provider"],
            "description": meta["description"],
            "signature": meta["signature"],
            "custom": meta.get("custom", False),
        }
        for meta in REGISTRY.values()
    ]


def get_tools(names: list[str] | None = None) -> list[Callable]:
    """Resolve registered tool callables, filtered by an optional allow-list."""
    load_tools()
    if not names:
        return [meta["function"] for meta in REGISTRY.values()]
    resolved = []
    for name in names:
        meta = REGISTRY.get(name)
        if meta:
            resolved.append(meta["function"])
    return resolved


def get_load_errors() -> dict[str, str]:
    """Return dictionary of tool load errors mapping filename to error message."""
    return dict(LOAD_ERRORS)


def get_provider_bindings() -> dict[str, str]:
    """Return dictionary of provider doorway bindings."""
    return dict(PROVIDER_BINDINGS)


def unknown_tool_names(names: list[str]) -> list[str]:
    """Return list of tool names that are not found in the registry."""
    load_tools()
    return [name for name in names if name not in REGISTRY]


def get_catalog_report() -> dict:
    """Generate a comprehensive catalog report without raising exceptions.

    Returns:
        {
            tools: list[dict],
            providers: dict[str, str],
            load_errors: dict[str, str],
            missing_agent_tools: dict[str, list[str]],
            warnings: list[str]
        }
    """
    try:
        load_tools()
    except Exception:
        pass

    tools = [
        {
            "name": meta["name"],
            "provider": meta["provider"],
            "description": meta["description"],
            "signature": meta["signature"],
            "custom": meta.get("custom", False),
        }
        for meta in REGISTRY.values()
    ]
    providers = dict(PROVIDER_BINDINGS)
    load_errors = dict(LOAD_ERRORS)
    missing_agent_tools: dict[str, list[str]] = {}
    warnings: list[str] = []

    for filename, err in load_errors.items():
        warnings.append(f"Failed to load tool module '{filename}': {err}")

    # Walk workspace/agents/*/agent.json and codebuilder/agents/*/agent.json
    agent_dirs = [
        REPO_ROOT / "workspace" / "agents",
        REPO_ROOT / "codebuilder" / "agents",
    ]
    for agents_dir in agent_dirs:
        try:
            if agents_dir.is_dir():
                for agent_file in sorted(agents_dir.glob("*/agent.json")):
                    try:
                        data = json.loads(agent_file.read_text(encoding="utf-8"))
                        agent_id = data.get("id") or agent_file.parent.name
                        req_tools = data.get("tools", [])
                        missing = [t for t in req_tools if t not in REGISTRY]
                        if missing:
                            missing_agent_tools[agent_id] = missing
                            warnings.append(
                                f"Agent '{agent_id}' references missing tools: {', '.join(missing)}"
                            )
                    except Exception as e:
                        warnings.append(f"Failed to parse '{agent_file}': {e}")
        except Exception as e:
            warnings.append(f"Failed to scan agent directory '{agents_dir}': {e}")

    return {
        "tools": tools,
        "providers": providers,
        "load_errors": load_errors,
        "missing_agent_tools": missing_agent_tools,
        "warnings": warnings,
    }
