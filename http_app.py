# http_app.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Any
import traceback, json
from starlette.concurrency import run_in_threadpool

# import agent safely
try:
    import agent   # agent.py must be at repo root
    AGENT_IMPORT_ERROR = None
except Exception as e:
    agent = None
    AGENT_IMPORT_ERROR = str(e)

app = FastAPI(title="LLM Quiz Agent Space")

class SolveRequest(BaseModel):
    email: str
    secret: str
    url: str
    data: Optional[Any] = None

@app.get("/")
def home():
    return {
        "status": "ok",
        "message": "LLM Quiz Agent Space Running",
        "agent_available": agent is not None,
        "agent_import_error": AGENT_IMPORT_ERROR
    }

@app.get("/debug")
def debug():
    return {
        "agent_mounted": agent is not None,
        "agent_import_error": AGENT_IMPORT_ERROR
    }

async def _call_agent(url: str, payload=None):
    if agent is None:
        raise RuntimeError("agent failed to import")

    fn = getattr(agent, "run_agent", None)
    if fn is None:
        raise RuntimeError("run_agent(url) not found in agent.py")

    def run_sync():
        try:
            return fn(url)
        except TypeError:
            return fn(url, payload)

    return await run_in_threadpool(run_sync)

@app.post("/agent/solve")
async def solve(req: SolveRequest):
    try:
        result = await _call_agent(req.url, req.data)
        return {"status": "ok", "result": str(result)}
    except Exception as e:
        return JSONResponse(
            {
                "detail": "agent error",
                "error": str(e),
                "traceback": traceback.format_exc()
            },
            status_code=500
        )