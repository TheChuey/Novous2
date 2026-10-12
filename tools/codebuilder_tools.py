"""CodeBuilder tools."""
import json

from core_engine.tool_catalog import tool


@tool(provider="codebuilder")
def run_python_code(code: str) -> str:
    """Run a Python snippet in CodeBuilder and return its output and diagnostics."""
    from codebuilder.execution import execute_python_code
    from codebuilder.schemas import CodeExecutionRequest

    result = execute_python_code(CodeExecutionRequest(code=code))
    return json.dumps(result.model_dump(), ensure_ascii=False)


@tool(provider="codebuilder")
def send_code_to_editor(code: str) -> str:
    """Queue generated Python code for insertion into the active CodeBuilder Monaco editor."""
    if not code.strip():
        raise ValueError("Code to send to the editor must not be empty.")
    return "CodeBuilder will insert this code into the active Monaco editor after the chat turn."


@tool(provider="codebuilder")
def run_code_in_editor() -> str:
    """Queue execution of the current contents of the active CodeBuilder editor."""
    return "CodeBuilder will run the active editor buffer after the chat turn."


def _codebuilder_host_supports_questionnaire() -> bool:
    try:
        from codebuilder import service
        return service.host_supports_questionnaire()
    except Exception:
        return False


if _codebuilder_host_supports_questionnaire():
    @tool(provider="codebuilder")
    def ask_user_questions(json_file_path: str, timeout_seconds: float = 300.0) -> str:
        """Pause the agent and ask the user a list of questions from a JSON file in the workspace.

        The browser pops up a step-by-step dialog; once the user submits answers this
        tool resumes and returns the questions and answers as a JSON string.

        Expected JSON file contents (a list, or an object with a "questions" list):
        [{"id": "q1", "question": "What is the target deployment environment?"}]
        Provide a workspace-root-relative path; do not prefix it with 'workspace/'.
        """
        from codebuilder import service
        return service.ask_user(json_file_path, timeout_seconds)

# Ask user questions is conditionally registered above based on host support.

