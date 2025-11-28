# tools/run_code.py

from google import genai
import subprocess
from langchain_core.tools import tool
from dotenv import load_dotenv
import os
import re
from decimal import Decimal, InvalidOperation
import logging
import sys
from google.genai import types

# Load environment variables
load_dotenv()

# Google GenAI client
client = genai.Client()

# Logger
logger = logging.getLogger(__name__)


# -------------------------------------------------------------
#  STRIP CODE FENCES
# -------------------------------------------------------------
def strip_code_fences(code: str) -> str:
    code = code.strip()
    if code.startswith("```"):
        code = code.split("\n", 1)[1]
    if code.endswith("```"):
        code = code.rsplit("\n", 1)[0]
    return code.strip()


# -------------------------------------------------------------
#  ROBUST NUMBER EXTRACTION + SUMMATION
# -------------------------------------------------------------

NUM_RE = re.compile(
    r'[-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)?(?:[eE][-+]?\d+)?'
    r'|[-+]?\d+\.\d+'
    r'|[-+]?\d+'
)


def parse_numbers_from_text(text: str):
    """Extract numbers from noisy transcript text."""
    if not text:
        return []

    raw_tokens = NUM_RE.findall(text)
    parsed = []

    for tok in raw_tokens:
        cleaned = tok.replace(",", "").strip()

        # Negative numbers in parentheses
        if cleaned.startswith("(") and cleaned.endswith(")"):
            cleaned = "-" + cleaned.strip("()")

        try:
            num = Decimal(cleaned)
            parsed.append((tok, num))
        except InvalidOperation:
            fallback = re.sub(r"[^0-9eE+\-.]", "", cleaned)
            try:
                num = Decimal(fallback)
                parsed.append((tok, num))
            except InvalidOperation:
                logger.debug(f"Failed to parse token: {tok}")

    return parsed


def robust_sum_from_text(text: str):
    parsed = parse_numbers_from_text(text)
    total = sum((n for (_, n) in parsed), Decimal(0))
    return total, parsed


# -------------------------------------------------------------
#  SAFE RUNTIME DIRECTORY (prevents uvicorn reload loops)
# -------------------------------------------------------------

def get_runtime_dir():
    """
    Writes runtime files outside the project tree so uvicorn --reload
    does NOT restart the server in the middle of the quiz.
    """
    outdir = os.path.expanduser("~/.llm_agent")
    os.makedirs(outdir, exist_ok=True)
    return outdir


# -------------------------------------------------------------
#  MAIN TOOL: EXECUTE PYTHON CODE
# -------------------------------------------------------------

@tool
def run_code(code: str) -> dict:
    """
    Executes Python code inside a safe temporary file.
    Returns stdout, stderr, return_code.
    """
    try:
        cleaned = strip_code_fences(code)

        runtime_dir = get_runtime_dir()
        filepath = os.path.join(runtime_dir, "runner.py")

        # Write code to runner file
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(cleaned)

        # Execute using the active Python interpreter from your venv
        proc = subprocess.Popen(
            [sys.executable, "runner.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=runtime_dir
        )

        stdout, stderr = proc.communicate(timeout=300)

        # Save outputs for debugging
        try:
            with open(os.path.join(runtime_dir, "last_runner_stdout.txt"), "w") as sf:
                sf.write(stdout or "")
            with open(os.path.join(runtime_dir, "last_runner_stderr.txt"), "w") as ef:
                ef.write(stderr or "")
        except Exception:
            logger.exception("Failed to write debug logs")

        return {
            "stdout": stdout,
            "stderr": stderr,
            "return_code": proc.returncode
        }

    except subprocess.TimeoutExpired as e:
        return {
            "stdout": e.stdout or "",
            "stderr": "TimeoutExpired: " + str(e),
            "return_code": -2
        }

    except Exception as e:
        logger.exception("run_code failed")
        return {
            "stdout": "",
            "stderr": str(e),
            "return_code": -1
        }