"""Agent tools backed by the shared workspace file manager."""

import json

from core_engine.tool_catalog import tool
from file_manager.service import file_manager_service


@tool(provider="file_manager")
def fm_list_directory(path: str = "") -> str:
    """List files and directories under the configured file-manager root using a relative path."""
    return json.dumps(file_manager_service.list_directory(path), indent=2)


@tool(provider="file_manager")
def fm_read_file(path: str) -> str:
    """Read a UTF-8 file using a path relative to the configured file-manager root."""
    return file_manager_service.read_file(path)["content"]


@tool(provider="file_manager")
def fm_write_file(path: str, content: str) -> str:
    """Write UTF-8 content under the configured file-manager root and return the result as JSON."""
    return json.dumps(file_manager_service.write_file(path, content), indent=2)
