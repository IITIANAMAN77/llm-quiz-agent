# agent.py
import os
from typing import TypedDict, Annotated, List, Any

from dotenv import load_dotenv
load_dotenv()

# Safe fallback for HF environment
EMAIL = os.getenv("EMAIL") or "23f2005127@ds.study.iitm.ac.in"
SECRET = os.getenv("SECRET") or "AMAN@131004"

RECURSION_LIMIT = 5000

# -----------------------------
# LangGraph + LangChain Imports
# -----------------------------
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.rate_limiters import InMemoryRateLimiter

# -----------------------------
# Import tools package
# -----------------------------
from tools import (
    get_rendered_html,
    download_file,
    post_request,
    run_code,
    add_dependencies
)
from tools.process_audio import process_audio

# Ensure tools list is correct
TOOLS = [
    run_code,
    get_rendered_html,
    download_file,
    post_request,
    add_dependencies,
    process_audio
]

# -----------------------------
# Agent State
# -----------------------------
class AgentState(TypedDict):
    messages: Annotated[List, add_messages]

# -----------------------------
# Gemini LLM with rate limiter
# -----------------------------
rate_limiter = InMemoryRateLimiter(
    requests_per_second=1/60,
    check_every_n_seconds=1,
    max_bucket_size=1
)

llm = init_chat_model(
    model_provider="google_genai",
    model="gemini-2.5-flash",
    rate_limiter=rate_limiter
).bind_tools(TOOLS)

# -----------------------------
# SYSTEM PROMPT
# -----------------------------
SYSTEM_PROMPT = f"""
You are an autonomous quiz-solving agent.

Your responsibilities:
1. Load the quiz page from the provided URL.
2. Extract all instructions, required parameters, submission rules, and the submit endpoint.
3. Solve the task exactly as required.
4. Submit the answer to the endpoint explicitly given in the task.
5. Read server response and continue if a new URL is given.
6. Only output "END" when the server no longer gives a new URL.

RULES:
- Never guess URLs.
- Never shorten or modify URLs.
- Never stop until no new URL is provided.
- Use provided tools only.
- Follow instructions exactly.
- Every request with email/secret use:
  Email: {EMAIL}
  Secret: {SECRET}

Output "END" only when the quiz is fully complete.
"""

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    MessagesPlaceholder(variable_name="messages")
])

llm_with_prompt = prompt | llm

# -----------------------------
# Agent Node
# -----------------------------
def agent_node(state: AgentState):
    """A single LLM step."""
    result = llm_with_prompt.invoke({"messages": state["messages"]})
    return {"messages": state["messages"] + [result]}

# -----------------------------
# Router Logic
# -----------------------------
def route(state: AgentState):
    """Decide whether next step is tool execution or LLM."""
    last = state["messages"][-1]

    # --- Detect tool calls ---
    tool_calls = None

    if hasattr(last, "tool_calls"):
        tool_calls = last.tool_calls
    elif isinstance(last, dict):
        tool_calls = last.get("tool_calls")

    if tool_calls:
        return "tools"

    # --- Detect END condition ---
    content = None
    if hasattr(last, "content"):
        content = last.content
    elif isinstance(last, dict):
        content = last.get("content")

    if isinstance(content, str) and content.strip() == "END":
        return END

    if isinstance(content, list):
        txt = content[0].get("text", "").strip()
        if txt == "END":
            return END

    return "agent"

# -----------------------------
# Build Graph
# -----------------------------
graph = StateGraph(AgentState)

graph.add_node("agent", agent_node)
graph.add_node("tools", ToolNode(TOOLS))

graph.add_edge(START, "agent")
graph.add_edge("tools", "agent")

graph.add_conditional_edges(
    "agent",
    route
)

app = graph.compile()

# -----------------------------
# Run-Agent entry (used by HF API)
# -----------------------------
def run_agent(url: str, payload: Any = None):
    """
    Main entry called by http_app.py
    Executes the entire agent workflow.
    """
    app.invoke(
        {"messages": [{"role": "user", "content": url}]},
        config={"recursion_limit": RECURSION_LIMIT},
    )
    return "Tasks completed successfully"