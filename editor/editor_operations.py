"""Physical file CRUD & Path Security for the editor pillar."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = REPO_ROOT / "workspace"
LIBRARY_ROOT = REPO_ROOT / "library"


def resolve_project_path(relative_path: str, root: Path | None = None) -> Path:
    if not relative_path:
        raise ValueError("A project-relative path is required.")

    clean_rel = relative_path.replace("\\", "/")
    if clean_rel == "library" or clean_rel.startswith("library/"):
        base_root = REPO_ROOT.resolve()
        allowed_root = LIBRARY_ROOT.resolve()
        candidate = (base_root / clean_rel).resolve()
        try:
            candidate.relative_to(allowed_root)
        except ValueError:
            raise ValueError(f"Access outside agent library '{allowed_root}' is forbidden.") from None
        return candidate

    base_root = (root or PROJECT_ROOT).resolve()
    candidate = (base_root / clean_rel).resolve()

    try:
        candidate.relative_to(base_root)
    except ValueError:
        raise ValueError(f"Access outside root path '{base_root}' is forbidden.")

    return candidate


def read_file_content(relative_path: str) -> dict:
    abs_path = resolve_project_path(relative_path)
    if not abs_path.is_file():
        raise FileNotFoundError(f"File not found: {relative_path}")
    content = abs_path.read_text(encoding="utf-8")
    return {"path": relative_path, "content": content}


def write_file_content(relative_path: str, content: str) -> dict:
    abs_path = resolve_project_path(relative_path)
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(content, encoding="utf-8")
    return {"path": relative_path, "bytes_written": len(content.encode('utf-8'))}


def delete_path(relative_path: str) -> dict:
    abs_path = resolve_project_path(relative_path)
    if abs_path.is_dir():
        if any(abs_path.iterdir()):
            raise IsADirectoryError(f"Directory not empty: {relative_path}")
        abs_path.rmdir()
    elif abs_path.is_file():
        abs_path.unlink()
    else:
        raise FileNotFoundError(f"Path not found: {relative_path}")
    return {"path": relative_path, "deleted": True}


def create_path(relative_path: str, kind: str = "file") -> dict:
    abs_path = resolve_project_path(relative_path)
    if abs_path.exists():
        raise FileExistsError(f"Path already exists: {relative_path}")
    if kind == "directory":
        abs_path.mkdir(parents=True)
    else:
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text("", encoding="utf-8")
    return {"path": relative_path, "created": kind}


def get_directory_tree(relative_path: str = "") -> dict:
    library_requested = relative_path == "library" or relative_path.startswith("library/")
    if library_requested:
        target_dir = resolve_project_path(relative_path)
        tree_root = LIBRARY_ROOT
        path_prefix = "library"
    else:
        target_dir = resolve_project_path(relative_path) if relative_path else PROJECT_ROOT
        tree_root = PROJECT_ROOT
        path_prefix = ""

    def _build_tree(p: Path):
        rel = str(p.relative_to(tree_root)).replace("\\", "/")
        if path_prefix:
            rel = path_prefix if rel == "." else f"{path_prefix}/{rel}"
        if p.is_file():
            return {"name": p.name, "type": "file", "path": rel}
        children = []
        for child in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            is_python_cache = child.is_dir() and child.name.lower() in {"__pycache__", "_pycache__"}
            if child.name.startswith(".") or is_python_cache or (
                child.is_file() and child.suffix.lower() == ".py"
            ):
                continue
            children.append(_build_tree(child))
        return {"name": p.name, "type": "directory", "path": rel, "children": children}

    if not target_dir.exists():
        raise FileNotFoundError(f"Directory not found: {relative_path}")
    result = _build_tree(target_dir)
    if not relative_path and LIBRARY_ROOT.is_dir():
        result["children"].append({
            "name": "library",
            "type": "directory",
            "path": "library",
            "children": [
                {
                    "name": file.name,
                    "type": "file",
                    "path": f"library/{file.name}",
                }
                for file in sorted(LIBRARY_ROOT.iterdir(), key=lambda item: item.name.lower())
                if file.is_file()
            ],
        })
    return result
