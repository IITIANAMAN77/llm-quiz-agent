# http_app.py
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Any
import traceback

# try to import your agent implementation
try:
    import agent   # ensures agent.py is importable from repo root
    AGENT_IMPORT_ERROR = None
except Exception as e:
    agent = None
    AGENT_IMPORT_ERROR = "".join(traceback.format_exception_only(type(e), e)).strip()

app = FastAPI(title="LLM Quiz Agent Space")

class SolveRequest(BaseModel):
    email: str
    secret: str
    url: str
    # add any other optional fields the agent expects
    data: Optional[Any] = None

@app.get("/")
def root():
    return {"status": "ok", "message": "LLM Quiz Agent Space Running", "agent_available": agent is not None, "agent_import_error": AGENT_IMPORT_ERROR}

@app.get("/debug")
def debug_info():
    return {"agent_mounted": agent is not None, "agent_import_error": AGENT_IMPORT_ERROR}

# Expose the solve route (calls your agent.run_agent or a wrapper)
@app.post("/agent/solve")
def agent_solve(req: SolveRequest):
    if agent is None:
        return JSONResponse({"detail": "agent import failed", "error": AGENT_IMPORT_ERROR}, status_code=500)

    # if your agent exposes run_agent(url) or similar adapt here
    try:
        # If agent has run_agent(url) that starts the workflow:
        result = agent.run_agent(req.url)
        return {"status": "ok", "result": result}
    except Exception as e:
        return JSONResponse({"detail": "agent error", "error": str(e)}, status_code=500)

    