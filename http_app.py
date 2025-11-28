# http_app.py — wrapper that calls agent.run_agent instead of mounting agent.app
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import traceback
import os

# Try to import run_agent (callable) from your agent module.
agent_available = False
agent_import_error = None
agent_run = None

try:
    # agent.run_agent(url: str) -> str
    from agent import run_agent as agent_run
    agent_available = True
except Exception as e:
    agent_import_error = str(e)
    agent_run = None
    agent_available = False

app = FastAPI(title="LLM Analysis Quiz - HTTP Wrapper (callable adapter)")

@app.get("/")
def root():
    return JSONResponse({
        "status": "ok",
        "message": "LLM Analysis Quiz agent wrapper running.",
        "agent_import_error": agent_import_error
    })

@app.get("/health")
def health():
    return JSONResponse({"status": "healthy", "agent_available": agent_available})

# Pydantic model for the incoming /agent/solve payload
class SolvePayload(BaseModel):
    email: str
    secret: str
    url: str

@app.post("/agent/solve")
def agent_solve(payload: SolvePayload):
    """
    Calls the underlying agent.run_agent(payload.url).
    Returns {"status":"ok"} on success or {"status":"error","reason":...} on failure.
    This keeps the HTTP wrapper simple and avoids mounting non-ASGI objects.
    """
    if not agent_available or agent_run is None:
        return JSONResponse(
            {"status": "error", "reason": "Agent not available", "agent_import_error": agent_import_error},
            status_code=500
        )

    try:
        # Run the agent synchronously with the provided URL.
        # agent.run_agent prints logs to stdout; it may run for up to a few minutes.
        agent_run(payload.url)
        return JSONResponse({"status": "ok"})
    except Exception as e:
        # Return the traceback to help debugging
        tb = traceback.format_exc()
        # Also write a small debug file
        try:
            outdir = os.path.expanduser("~/.llm_agent")
            os.makedirs(outdir, exist_ok=True)
            with open(os.path.join(outdir, "last_agent_exception.txt"), "w", encoding="utf8") as f:
                f.write(tb)
        except Exception:
            pass
        return JSONResponse({"status": "error", "reason": str(e), "traceback": tb}, status_code=500)