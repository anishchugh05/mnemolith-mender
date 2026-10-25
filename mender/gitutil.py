import subprocess
from pathlib import Path
from typing import Optional
from . import config

def _git(*args: str) -> Optional[str]:
    r = subprocess.run(["git", *args], cwd=config.REPO,
                       capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None

def safe_path(rel: str) -> Optional[Path]:
    """Resolve a repo-relative path; refuse anything outside the repo."""
    p = (config.REPO / rel).resolve()
    return p if p == config.REPO or config.REPO in p.parents else None

def blob(hash_: Optional[str]) -> Optional[str]:
    """Old file content from a saved blob hash (None if never committed)."""
    if not hash_:
        return None
    return _git("cat-file", "-p", hash_)

def working(rel: str) -> Optional[str]:
    p = safe_path(rel)
    if not p or not p.is_file():
        return None
    try:
        return p.read_text(errors="replace")
    except OSError:
        return None

def diff_head(rel: str) -> str:
    return _git("diff", "HEAD", "--", rel) or ""

def log(rel: str, n: int = 5) -> str:
    return _git("log", f"-{n}", "--oneline", "--", rel) or ""