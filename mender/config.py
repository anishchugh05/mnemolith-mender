import os
import subprocess
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()                                   # nearest .env above this file
load_dotenv(Path.cwd() / ".env")                # or one in the folder you run from
load_dotenv(Path.home() / ".config" / "mender" / ".env")   # or a per-user one

BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
API_KEY = os.environ.get("NEBIUS_API_KEY", "")
TAVILY_KEY = os.environ.get("TAVILY_API_KEY", "")

# Confirm exact IDs in the Token Factory catalog
MODEL_NANO = os.environ.get("MENDER_NANO", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B")
MODEL_ULTRA = os.environ.get("MENDER_ULTRA", "nvidia/Nemotron-3-Ultra-550b-a55b")

# Mnemolith's file paths are relative to the git repo's top folder, so Mender uses that too.
_start = Path(os.environ.get("MENDER_REPO", ".")).resolve()
_top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=_start, capture_output=True, text=True)
REPO = Path(_top.stdout.strip()) if _top.returncode == 0 else _start
STATE_DIR = REPO / ".mender"
CALL_LOG = STATE_DIR / "calls.jsonl"
QUEUE_FILE = STATE_DIR / "queue.json"

MAX_AGENT_STEPS = 8
MAX_FILE_CHARS = 12000   # truncate big files before sending to a model