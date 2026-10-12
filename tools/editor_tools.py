"""Editor tools."""
from core_engine import langgraph_tools
from core_engine.tool_catalog import tool


@tool(provider="editor")
def read_file(path: str) -> str:
    """Read a file by workspace-root-relative path; do not prefix paths with 'workspace/'."""
    return langgraph_tools.read_file_tool.invoke({"relative_path": path})


@tool(provider="editor")
def write_file(path: str, content: str) -> str:
    """Write and verify non-empty text at a workspace-root-relative path; bare filenames go in the root.

    Do not prefix paths with 'workspace/'.
    Supports formats such as .txt, .md, .py, .json, .html, .css, and .js.
    Use create_file only when an intentionally empty file is requested.
    """
    return langgraph_tools.write_file_tool.invoke(
        {"relative_path": path, "content": content}
    )


@tool(provider="editor")
def create_file(path: str, kind: str = "file") -> str:
    """Create an empty file or directory by workspace-root-relative path; bare names go in root. Use write_file for content."""
    return langgraph_tools.create_file_tool.invoke(
        {"relative_path": path, "kind": kind}
    )


@tool(provider="editor")
def delete_file(path: str) -> str:
    """Delete a file or empty directory from the workspace."""
    return langgraph_tools.delete_file_tool.invoke({"relative_path": path})


@tool(provider="editor")
def list_directory(path: str = "") -> str:
    """List the workspace directory tree (optionally rooted at a relative path)."""
    return langgraph_tools.map_directory_tree_tool.invoke({"relative_path": path})


@tool(provider="editor")
def extract_docstrings(path: str) -> str:
    """Parse Python code AST to extract module, class, and function docstrings."""
    return langgraph_tools.extract_docstrings_tool.invoke({"relative_path": path})


@tool(provider="editor")
def search_workspace(query: str, extension: str = ".py") -> str:
    """Search workspace files for matching keyword or snippet."""
    return langgraph_tools.search_workspace_tool.invoke(
        {"query": query, "extension": extension}
    )
