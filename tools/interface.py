"""Tools interface: FastAPI router and Python doorway for tool registry."""

import ast
import inspect
from pathlib import Path
import re
from typing import Callable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core_engine import tool_catalog

router = APIRouter()

PROMOTED_MODULE_PATH = Path(__file__).resolve().parent / "promoted.py"
PROMOTED_MARKER = "# PROMOTION_MARKER: tools appended below will be registered as custom tools"
REPO_ROOT = Path(__file__).resolve().parent.parent

_FUNCTION_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class RegisterToolRequest(BaseModel):
    source: str = Field(..., min_length=1, max_length=50000)
    name: str | None = None


def _ensure_promoted_file() -> None:
    if not PROMOTED_MODULE_PATH.exists():
        PROMOTED_MODULE_PATH.write_text(
            '"""Custom tools promoted from the Function Testing Workbench."""\n'
            'from core_engine.tool_catalog import tool\n\n'
            f"{PROMOTED_MARKER}\n\n",
            encoding="utf-8",
            newline="\n",
        )
    else:
        content = PROMOTED_MODULE_PATH.read_text(encoding="utf-8")
        if PROMOTED_MARKER not in content:
            sep = "\n\n" if not content.endswith("\n") else "\n"
            PROMOTED_MODULE_PATH.write_text(
                content + sep + PROMOTED_MARKER + "\n\n",
                encoding="utf-8",
                newline="\n",
            )


def list_promoted_tool_names() -> list[str]:
    """Return list of tool function names defined in promoted.py."""
    if not PROMOTED_MODULE_PATH.is_file():
        return []
    try:
        source = PROMOTED_MODULE_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception:
        return []
    names = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            names.append(node.name)
    return names


def _decorated_source(first: str, second: str = "") -> str:
    """Ensure tool source has the @tool decorator."""
    source = second if second else first
    src = source.strip()
    if src.startswith("@tool"):
        return src + "\n"
    return f"@tool\n{src}\n"


def _function_span(source: str, name: str) -> tuple[int, int, ast.FunctionDef]:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            start_line = min(
                (decorator.lineno for decorator in node.decorator_list),
                default=node.lineno,
            )
            return start_line - 1, node.end_lineno, node
    raise FileNotFoundError(f"Custom tool '{name}' was not found in the promoted module.")


def _function_source(source: str, name: str) -> str:
    start, end, _ = _function_span(source, name)
    return "\n".join(source.splitlines()[start:end]).strip() + "\n"


def _source_for_name(name: str, full_source: str) -> str:
    return _function_source(full_source, name)


def _remove_function(source: str, name: str) -> str:
    start, end, _ = _function_span(source, name)
    lines = source.splitlines(keepends=True)
    while end < len(lines) and lines[end].strip() == "":
        end += 1
    del lines[start:end]
    return "".join(lines)


def register_tool(source: str, name: str | None = None) -> dict:
    """Register a custom tool by appending to promoted.py and execing into tool_catalog."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError(f"Python syntax error: {exc}") from exc

    fn_node = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            fn_node = node
            break
    if fn_node is None:
        raise ValueError("Define at least one public top-level function.")

    func_name = fn_node.name
    if name and name != func_name:
        raise HTTPException(
            status_code=400,
            detail="The primary function changed; run the test again before adding it.",
        )
    name = func_name

    tool_catalog.load_tools()
    if name in tool_catalog.REGISTRY:
        raise HTTPException(
            status_code=409, detail=f"Tool '{name}' is already registered."
        )

    _ensure_promoted_file()
    previous_content = PROMOTED_MODULE_PATH.read_text(encoding="utf-8")
    block = _decorated_source(name, source)
    sep = "\n" if not previous_content.endswith("\n\n") else ""
    new_content = previous_content + sep + block + "\n"
    PROMOTED_MODULE_PATH.write_text(new_content, encoding="utf-8", newline="\n")

    try:
        exec(block, tool_catalog.__dict__)
    except Exception as exc:
        PROMOTED_MODULE_PATH.write_text(previous_content, encoding="utf-8", newline="\n")
        tool_catalog.REGISTRY.pop(name, None)
        raise ValueError(f"Failed to execute tool '{name}': {exc}") from exc

    fn = tool_catalog.REGISTRY[name]["function"]
    tool_catalog.REGISTRY[name]["custom"] = True
    return {
        "name": name,
        "path": "tools/promoted.py",
        "description": ast.get_docstring(fn_node) or "",
        "signature": str(inspect.signature(fn)),
    }


def remove_tool(name: str) -> dict:
    """Remove a custom tool from promoted.py and tool_catalog.REGISTRY."""
    tool_catalog.load_tools()
    if name not in tool_catalog.REGISTRY:
        raise HTTPException(status_code=404, detail=f"Tool '{name}' not found.")

    _ensure_promoted_file()
    previous_content = PROMOTED_MODULE_PATH.read_text(encoding="utf-8")
    try:
        new_content = _remove_function(previous_content, name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        PROMOTED_MODULE_PATH.write_text(new_content, encoding="utf-8", newline="\n")
    except Exception as exc:
        PROMOTED_MODULE_PATH.write_text(previous_content, encoding="utf-8", newline="\n")
        raise OSError(f"Could not update promoted module: {exc}") from exc

    tool_catalog.REGISTRY.pop(name, None)
    return {
        "name": name,
        "path": "tools/promoted.py",
        "deleted": True,
    }


def get_tool_source(name: str) -> dict:
    """Retrieve source code of a tool (either promoted or builtin)."""
    if not _FUNCTION_NAME.fullmatch(name):
        raise ValueError("The tool name is not valid.")

    if PROMOTED_MODULE_PATH.is_file():
        full_source = PROMOTED_MODULE_PATH.read_text(encoding="utf-8")
        try:
            source = _function_source(full_source, name)
            return {
                "name": name,
                "path": "tools/promoted.py",
                "source": source,
            }
        except FileNotFoundError:
            pass

    tool_catalog.load_tools()
    meta = tool_catalog.REGISTRY.get(name)
    if meta and "function" in meta:
        fn = meta["function"]
        try:
            source = inspect.getsource(fn)
            sourcefile = inspect.getsourcefile(fn)
            rel_path = (
                str(Path(sourcefile).relative_to(REPO_ROOT).as_posix())
                if sourcefile
                else "tools"
            )
            return {
                "name": name,
                "path": rel_path,
                "source": source,
            }
        except Exception:
            pass

    raise FileNotFoundError(f"Custom tool '{name}' was not found.")


def list_tools() -> list[dict]:
    """Return tools list with custom overlay from promoted.py."""
    tool_catalog.load_tools()
    promoted = set(list_promoted_tool_names())
    tools = []
    for meta in tool_catalog.REGISTRY.values():
        tools.append({
            "name": meta["name"],
            "provider": meta["provider"],
            "description": meta["description"],
            "signature": meta["signature"],
            "custom": meta["name"] in promoted or meta.get("custom", False),
        })
    return tools


def get_tool(name: str) -> Callable | None:
    """Resolve registered tool callable."""
    tool_catalog.load_tools()
    meta = tool_catalog.REGISTRY.get(name)
    return meta["function"] if meta else None


def provider_bindings() -> dict[str, str]:
    """Return provider mappings."""
    return tool_catalog.get_provider_bindings()


def catalog_report() -> dict:
    """Return catalog diagnostic report."""
    return tool_catalog.get_catalog_report()


@router.get("/api/tools")
def api_list_tools():
    rep = catalog_report()
    return {
        "tools": list_tools(),
        "providers": provider_bindings(),
        "warnings": rep.get("warnings", []),
    }


@router.get("/api/tools/health")
def api_tools_health():
    errors = tool_catalog.get_load_errors()
    return {
        "status": "healthy" if not errors else "degraded",
        "load_errors": errors,
        "warnings": catalog_report().get("warnings", []),
    }


@router.post("/api/tools/register")
def api_register_tool(req: RegisterToolRequest):
    try:
        return register_tool(req.source, req.name)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/tools/{name}")
def api_get_tool(name: str):
    tool_catalog.load_tools()
    meta = tool_catalog.REGISTRY.get(name)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Tool '{name}' not found.")
    promoted = set(list_promoted_tool_names())
    return {
        "name": meta["name"],
        "provider": meta["provider"],
        "description": meta["description"],
        "signature": meta["signature"],
        "custom": meta["name"] in promoted or meta.get("custom", False),
    }


@router.delete("/api/tools/{name}")
def api_delete_tool(name: str):
    try:
        return remove_tool(name)
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
