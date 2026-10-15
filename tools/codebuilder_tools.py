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
  import json

def ask_user_questions(question_list):
    """
    Ask the user a list of questions through the command line.

    Args:
        question_list (list): A list of dictionaries containing
                              'id' and 'question' fields.

    Returns:
        list: A list of dictionaries containing question IDs and answers.
    """
    answers = []

    for question in question_list:
        question_id = question.get("id", "unknown")
        question_text = question.get("question", "")

        try:
            answer = input(f"{question_text} ").strip()

            if not answer:
                answer = "No answer provided"

        except EOFError:
            answer = "No answer provided"

        answers.append({
            "id": question_id,
            "answer": answer
        })

    return answers


def ask_user_questions_cli(json_data):
    """
    Accept JSON input, ask the questions, and return JSON answers.

    Args:
        json_data (str): A JSON string containing a list of questions.

    Returns:
        str | None: JSON string containing answers, or None on failure.
    """
    try:
        questions = json.loads(json_data)

        if not isinstance(questions, list):
            print("Error: Input must be a JSON list of questions.")
            return None

        for question in questions:
            if not isinstance(question, dict):
                print("Error: Each question must be a JSON object.")
                return None

            if "question" not in question:
                print("Error: Each question must contain a 'question' field.")
                return None

            if not isinstance(question["question"], str):
                print("Error: Each question must be a string.")
                return None

        answers = ask_user_questions(questions)

        return json.dumps(answers, ensure_ascii=False)

    except json.JSONDecodeError:
        print("Error: Invalid JSON data.")
        return None
