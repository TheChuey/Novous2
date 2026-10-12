"""Core engine tools."""
import ast
import json
import operator

from core_engine import langgraph_tools
from core_engine.agent_factory import load_agent
from core_engine.tool_catalog import tool


_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(expr: str):
    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
            return _OPERATORS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
            return _OPERATORS[type(node.op)](_eval(node.operand))
        raise ValueError(f"Unsupported expression element: {ast.dump(node)}")

    return _eval(ast.parse(expr, mode="eval"))


@tool(provider="core_engine")
def calculator(expression: str) -> str:
    """Evaluate a basic arithmetic expression (numbers, + - * / // % ** and parentheses)."""
    result = _safe_eval(expression)
    return f"{expression} = {result}"


@tool(provider="core_engine")
def docling_parse(path: str, output_format: str = "markdown") -> str:
    """Parse PDF, DOCX, PPTX, or HTML files into structured Markdown/JSON via Docling."""
    return langgraph_tools.docling_parse_tool.invoke(
        {"relative_path": path, "output_format": output_format}
    )


@tool(provider="core_engine")
def rag_agent_tool(query: str, relative_path: str = "", top_k: int = 3) -> str:
    """Query workspace knowledge base or parse a document via Docling for relevant passages."""
    return langgraph_tools.rag_agent_tool.invoke(
        {"query": query, "relative_path": relative_path, "top_k": top_k}
    )


@tool(provider="core_engine")
def agent_info(agent_id: str) -> str:
    """Return the metadata and composed system prompt of a workspace agent."""
    profile = load_agent(agent_id)
    return json.dumps(
        {
            "id": profile.id,
            "name": profile.name,
            "mode": profile.mode,
            "description": profile.description,
            "role": profile.role,
            "purpose": profile.purpose,
            "boundaries": profile.boundaries,
            "system_prompt": profile.system_prompt,
        },
        indent=2,
    )
