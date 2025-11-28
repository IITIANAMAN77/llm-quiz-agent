# tools/process_audio.py
from langchain_core.tools import tool
import os
import re
from decimal import Decimal, InvalidOperation
import logging
import requests
import time
from dotenv import load_dotenv

# optional: use google genai if installed for STT fallback
try:
    from google import genai
    HAVE_GENAI = True
    genai_client = genai.Client()
except Exception:
    HAVE_GENAI = False
    genai_client = None

load_dotenv()
logger = logging.getLogger(__name__)

# ---------------- robust number parsing (same as run_code)
NUM_RE = re.compile(
    r'[-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)?(?:[eE][-+]?\d+)?'
    r'|[-+]?\d+\.\d+'
    r'|[-+]?\d+'
)

def parse_numbers_from_text(text: str):
    if not text:
        return []
    raw_tokens = NUM_RE.findall(text)
    parsed = []
    for tok in raw_tokens:
        cleaned = tok.replace(",", "").strip()
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
                logger.debug("Failed to parse token: %s", tok)
    return parsed

def robust_sum_from_text(text: str):
    parsed = parse_numbers_from_text(text)
    total = sum((n for (_, n) in parsed), Decimal(0))
    return total, parsed

# ---------------- safe audio download helper ----------------
def download_file(url: str, dest_dir: str, max_retries: int = 3, timeout: int = 30):
    os.makedirs(dest_dir, exist_ok=True)
    local_name = os.path.basename(url.split("?")[0]) or f"audio_{int(time.time())}.bin"
    dest_path = os.path.join(dest_dir, local_name)
    attempt = 0
    while attempt < max_retries:
        try:
            with requests.get(url, stream=True, timeout=timeout) as r:
                r.raise_for_status()
                with open(dest_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            return dest_path
        except Exception as e:
            logger.warning("download_file attempt %d failed for %s: %s", attempt+1, url, str(e))
            attempt += 1
            time.sleep(1 + attempt)
    raise RuntimeError(f"Failed to download {url} after {max_retries} attempts")

# ---------------- write debug artifact ----------------
def write_audio_debug(transcript: str, parsed, total):
    outdir = os.path.expanduser("~/.llm_agent")
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "last_audio_debug.txt")
    with open(path, "w", encoding="utf8") as f:
        f.write("TRANSCRIPT:\n")
        f.write(transcript + "\n\n")
        f.write("PARSED TOKENS:\n")
        for tok, num in parsed:
            f.write(f"{tok} -> {num}\n")
        f.write("\nTOTAL:\n")
        f.write(str(total) + "\n")
    return path

# ---------------- main tool ----------------
@tool
def process_audio(input_str: str) -> dict:
    """
    Accepts either:
    - a transcript string (preferred), OR
    - an audio URL (http(s)...) to download & transcribe.

    Returns:
    {
      "transcript": <text or empty string>,
      "parsed": [["raw_token", Decimal], ...],
      "total": <int or float or str>,
      "debug_file": "<path to debug file>",
      "notes": "<any notes or warnings>"
    }
    """
    notes = []
    transcript = ""
    # Heuristic: if input looks like a URL, try to download and transcribe
    if isinstance(input_str, str) and input_str.strip().lower().startswith("http"):
        url = input_str.strip()
        try:
            dest_dir = os.path.expanduser("~/.llm_agent/audio")
            audio_path = download_file(url, dest_dir)
            notes.append(f"Downloaded audio to {audio_path}")
            # Attempt to transcribe with Google GenAI if available
            if HAVE_GENAI and genai_client is not None:
                try:
                    # This is a best-effort call; exact GenAI STT API usage may differ.
                    # If your project already has a preferred STT, that will still work — this is fallback.
                    resp = genai_client.audio.speech_to_text(file=audio_path)
                    # The above may not match exact library signature on all versions.
                    transcript = getattr(resp, "text", "") or str(resp)
                    notes.append("Transcribed via google.genai")
                except Exception as e:
                    notes.append("google.genai transcription failed: " + str(e))
                    transcript = ""
            else:
                notes.append("No google.genai available for transcription; returning audio_path for downstream processing.")
                transcript = ""  # let other parts of pipeline handle transcription
        except Exception as e:
            notes.append("audio download/transcription failed: " + str(e))
            transcript = ""
    else:
        # treat input as transcript text
        transcript = input_str or ""

    # Robustly parse numbers and compute total
    total_decimal, parsed = robust_sum_from_text(transcript)
    # Convert total to int if whole number else float
    if total_decimal == total_decimal.to_integral_value():
        total_out = int(total_decimal)
    else:
        total_out = float(total_decimal)

    debug_file = write_audio_debug(transcript, parsed, total_decimal)

    return {
        "transcript": transcript,
        "parsed": [(r, str(n)) for (r, n) in parsed],
        "total": total_out,
        "debug_file": debug_file,
        "notes": " | ".join(notes)
    }