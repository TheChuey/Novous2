"""Read-only folder/file mapping tools restricted to an allow-list of root paths.

Allowed roots live in allowed_paths.json (next to this file) under "map_roots" and are
re-read on every call, so edits take effect without restarting the server.
"""
import ast
import json
import os
from datetime import datetime
from pathlib import Path

from core_engine.tool_catalog import tool

CONFIG_PATH = Path(__file__).resolve().parent / "allowed_paths.json"
MAX_DEPTH = 6
MAX_ENTRIES = 5000
PAGE_SIZE = 80
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}


def _allowed_roots() -> list[Path]:
    if not CONFIG_PATH.is_file():
        return []
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    roots = []
    for raw in data.get("map_roots", []):
        try:
            roots.append(Path(os.path.expandvars(str(raw))).expanduser().resolve())
        except OSError:
            continue
    return roots


def _within(path: Path, root: Path) -> bool:
    return os.path.normcase(str(path)) == os.path.normcase(str(root)) or any(
        os.path.normcase(str(parent)) == os.path.normcase(str(root))
        for parent in path.parents
    )


def _resolve_allowed(raw_path: str) -> Path:
    """Resolve a path (following symlinks) and require it to be inside an allowed root."""
    if not raw_path or not raw_path.strip():
        raise ValueError("A path is required.")
    roots = _allowed_roots()
    if not roots:
        raise PermissionError(f"No allowed paths configured in {CONFIG_PATH}.")
    candidate = Path(os.path.expandvars(raw_path.strip())).expanduser().resolve()
    if not any(_within(candidate, root) for root in roots):
        allowed = ", ".join(str(r) for r in roots)
        raise PermissionError(f"Path '{candidate}' is outside the allowed paths: {allowed}")
    return candidate


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def _visible_entries(directory: Path, roots: list[Path], include_files: bool) -> list[tuple[Path, bool]]:
    try:
        entries = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError:
        return []
    visible = []
    for entry in entries:
        try:
            resolved = entry.resolve()
            if not any(_within(resolved, root) for root in roots):
                continue  # links pointing outside the allowed roots are not followed
            if entry.is_dir():
                if entry.name not in SKIP_DIRS:
                    visible.append((resolved, True))
            elif include_files and entry.is_file():
                visible.append((resolved, False))
        except OSError:
            continue
    return visible


def _build_lines(directory: Path, roots: list[Path], depth: int, include_files: bool,
                 prefix: str, lines: list[str], counter: list[int]) -> None:
    entries = _visible_entries(directory, roots, include_files)
    for index, (entry, is_dir) in enumerate(entries):
        last = index == len(entries) - 1
        if counter[0] >= MAX_ENTRIES:
            lines.append(f"{prefix}└── … scan limit of {MAX_ENTRIES} entries reached")
            return
        counter[0] += 1
        connector = "└── " if last else "├── "
        if is_dir:
            lines.append(f"{prefix}{connector}📁 {entry.name}/")
            if depth > 1:
                _build_lines(entry, roots, depth - 1, include_files,
                             prefix + ("    " if last else "│   "), lines, counter)
        else:
            try:
                size = f"  ({_format_size(entry.stat().st_size)})"
            except OSError:
                size = ""
            lines.append(f"{prefix}{connector}📄 {entry.name}{size}")


def render_map_page(path: str, max_depth: int = 3, include_files: bool = True,
                    offset: int = 0, page_size: int = PAGE_SIZE) -> dict:
    """Return one page of the folder tree as text plus paging info. Raises on disallowed paths."""
    target = _resolve_allowed(path)
    if not target.is_dir():
        raise NotADirectoryError(f"'{target}' is not a directory.")
    depth = max(1, min(int(max_depth), MAX_DEPTH))
    start = max(0, int(offset))
    size = max(10, min(int(page_size), 500))

    lines = [f"📁 {target}"]
    _build_lines(target, _allowed_roots(), depth, bool(include_files), "", lines, [0])
    page = lines[start:start + size]
    next_offset = start + len(page)
    remaining = max(0, len(lines) - next_offset)
    text = "\n".join(page)
    if not page:
        text = "(no more entries)"
    elif len(lines) == 1:
        text += "\n└── (empty)"
    return {"text": text, "next_offset": next_offset, "remaining": remaining, "total": len(lines)}


@tool(provider="tools")
def list_allowed_paths() -> str:
    """List the root paths that the map tools are permitted to read."""
    return json.dumps([str(root) for root in _allowed_roots()], indent=2)


def _to_int(value, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _to_bool(value, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("true", "1", "yes", "y"):
        return True
    if text in ("false", "0", "no", "n"):
        return False
    return default


@tool(provider="tools")
def map_folder(path: str, max_depth: int = 3, include_files: bool = True, offset: int = 0) -> str:
    """Draw a folder (absolute path like C:\\Users\\...) as a tree of folders and files; use this instead of list_directory for absolute paths.

    The path must be inside an allowed path (see list_allowed_paths).
    The chat shows the tree to the user automatically, so do not retype it. Output is paged (80 lines).
    If it ends with a "more lines" note, ask the user whether they want more; if yes, call map_folder
    again with the same arguments and offset set to the "next offset" value. Depth is capped at 6.
    Only path is required; omit the other arguments for defaults.
    """
    try:
        page = render_map_page(
            path, _to_int(max_depth, 3), _to_bool(include_files), _to_int(offset, 0)
        )
    except Exception as exc:
        raise RuntimeError(f"Could not map folder '{path}': {exc}") from exc
    text = page["text"]
    if page["remaining"]:
        text += f"\n… {page['remaining']} more lines (next offset {page['next_offset']})"
    return text


map_folder.display_output = True


@tool(provider="tools")
def map_file(path: str) -> str:
    """Describe a file (size, modified time, Python classes/functions) at an absolute path inside an allowed path."""
    try:
        target = _resolve_allowed(path)
        if not target.is_file():
            return f"Error: '{target}' is not a file."
        stat = target.stat()
        info = {
            "path": str(target),
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            "extension": target.suffix.lower(),
        }
        if target.suffix.lower() == ".py":
            tree = ast.parse(target.read_text(encoding="utf-8", errors="ignore"))
            info["classes"] = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
            info["functions"] = [
                n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
        return json.dumps(info, indent=2)
    except Exception as exc:
        return f"Error mapping file '{path}': {exc}"
