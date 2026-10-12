"""CodeBuilder doorway: the HTTP adapter. Routing, status codes and SSE framing only.

Layer rule: no business logic here. Each endpoint validates transport concerns and
delegates to ``service`` (use-cases) or ``execution`` (the engine).
"""

import json
from typing import Iterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from . import service
from .execution import cancel_run, execute_python_code, run_stream
from .schemas import CodeExecutionRequest, CodeExecutionResult, StructuredEditRequest

router = APIRouter(prefix="/api/codebuilder", tags=["CodeBuilder"])


@router.get("/health")
def api_codebuilder_health():
    """Return the health state of the CodeBuilder pillar."""
    return service.health()


@router.get("/agent")
def api_get_agent():
    """Return the CodeBuilder specialist profile."""
    return service.agent_meta()


@router.get("/agents")
def api_codebuilder_agents():
    """List only agents stored in the CodeBuilder environment."""
    return {"agents": service.list_agents()}


@router.post("/execute", response_model=CodeExecutionResult)
def api_execute_code(req: CodeExecutionRequest):
    """Execute Python source (isolated, time-limited) and return output and diagnostics."""
    try:
        return execute_python_code(req)
    except Exception as exc:  # pragma: no cover - surfaced as HTTP 500
        raise HTTPException(status_code=500, detail=f"CodeBuilder execution error: {exc}") from exc


def _sse(events: Iterator[dict]) -> Iterator[str]:
    try:
        for event in events:
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    finally:
        events.close()  # client went away -> engine kills the process tree


@router.post("/execute/stream")
def api_stream_execute(req: CodeExecutionRequest):
    """Stream risky-mode execution output live as Server-Sent Events."""
    if req.mode != "risky":
        raise HTTPException(status_code=400, detail="Streaming is only supported in risky mode.")
    return StreamingResponse(
        _sse(run_stream(req)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/execute/{run_id}/cancel")
def api_cancel_run(run_id: str):
    """Stop a live run (use the ``run_id`` from the stream's ``start`` event)."""
    if not cancel_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found or already finished.")
    return {"run_id": run_id, "cancelled": True}


@router.post("/edit")
def api_apply_structured_edit(req: StructuredEditRequest):
    """Write an approved file update to the workspace."""
    try:
        return service.apply_edit(req)
    except service.EditRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not write file: {exc}") from exc
