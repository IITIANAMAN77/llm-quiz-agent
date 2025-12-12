# http_app.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Any, Dict
import traceback
import json

# concurrency helper — runs blocking code in a threadpool safely
from starlette.concurrency import run_in_threadpool

# Attempt to import your agent implementation (agent.py) from repo root
try:
    import agent  # your agent module (must define run_agent or similar)
    AGENT_IMPORT_ERROR = None
except Exception as e:
    agent = None
    AGENT_IMPORT_ERROR = "".join(traceback.format_exception_only(type(e), e)).strip()

app = FastAPI(title="LLM Quiz Agent Space")

class SolveRequest(BaseModel):
    email: str
    secret: str
    url: str
    # optional arbitrary payload the agent might accept
    data: Optional[Any] = None

@app.get("/")
def root():
    """
    Basic health/status endpoint. Shows whether agent module is importable.
    """
    return {
        "status": "ok",
        "message": "LLM Quiz Agent Space Running",
        "agent_available": agent is not None,
        "agent_import_error": AGENT_IMPORT_ERROR
    }

@app.get("/debug")
def debug_info():
    """
    Debug endpoint to inspect if agent imported correctly.
    """
    return {
        "agent_mounted": agent is not None,
        "agent_import_error": AGENT_IMPORT_ERROR
    }


async def _invoke_agent_run(url: str, payload: Optional[Dict] = None):
    """
    Helper to call agent.run_agent in a threadpool to avoid blocking the event loop.
    Returns the result (whatever run_agent returns).
    """
    if agent is None:
        raise RuntimeError("agent module not available")

    # Prefer calling run_agent(url) if available
    if hasattr(agent, "run_agent"):
        # If run_agent accepts two args (url, payload) support that, else call with url
        fn = getattr(agent, "run_agent")
        try:
            # examine signature length len(...) is not robust; we'll try both ways gracefully
            # call in threadpool to avoid blocking
            def call_sync():
                try:
                    # try calling with both args
                    return fn(url, payload)  # many implementations accept (url) only; if payload unused it's fine
                except TypeError:
                    # fallback to calling with only url
                    return fn(url)
            return await run_in_threadpool(call_sync)
        except Exception as e:
            # bubble up with traceback
            raise
    else:
        raise RuntimeError("agent module does not expose run_agent(url)")


@app.post("/agent/solve")
async def agent_solve(req: SolveRequest):
    """
    Primary route used by the quiz system.
    This will call agent.run_agent(req.url) (or agent.run_agent(url, data) if agent supports it).
    Returns JSON with result or an error object.
    """
    if agent is None:
        return JSONResponse(
            content={"detail": "agent import failed", "error": AGENT_IMPORT_ERROR},
            status_code=500
        )

    try:
        # call run_agent in background thread
        result = await _invoke_agent_run(req.url, payload=req.data if req.data is not None else None)
        # Normalize result if it's not JSON serializable
        try:
            json.dumps(result)  # if this fails, wrap into string
            safe_result = result
        except Exception:
            safe_result = {"result_str": str(result)}

        return {"status": "ok", "result": safe_result}
    except Exception as e:
        tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        return JSONResponse(
            content={"detail": "agent error", "error": str(e), "traceback": tb},
            status_code=500
        )

# alias top-level /solve to same behavior (some clients call /solve)
@app.post("/solve")
async def solve_alias(req: SolveRequest):
    return await agent_solve(req)

# Extra: accept raw POSTs (no JSON schema) and forward to agent (useful for curling raw body)
@app.post("/agent/solve-raw")
async def agent_solve_raw(request: Request):
    """
    Accept any JSON body (no strict schema) and attempt to call run_agent.
    Use this if quiz system sends different keys.
    """
    if agent is None:
        return JSONResponse({"detail": "agent import failed", "error": AGENT_IMPORT_ERROR}, status_code=500)

    try:
        body_bytes = await request.body()
        if not body_bytes:
            return JSONResponse({"detail": "empty body"}, status_code=400)

        try:
            payload = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            # not JSON — pass raw string as payload
            payload = body_bytes.decode("utf-8", errors="ignore")

        # Expecting payload to include url / email / secret; try to extract url
        url = None
        if isinstance(payload, dict):
            url = payload.get("url")
        if not url:
            return JSONResponse({"detail": "missing url in payload"}, status_code=422)

        result = await _invoke_agent_run(url, payload=payload)
        try:
            json.dumps(result)
            safe_result = result
        except Exception:
            safe_result = {"result_str": str(result)}
        return {"status": "ok", "result": safe_result}
    except Exception as e:
        tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        return JSONResponse({"detail": "agent error", "error": str(e), "traceback": tb}, status_code=500)