import subprocess
from pathlib import Path
from typing import Optional
from . import config

def _git(*args: str, stdin: Optional[str] = None) -> Optional[str]:
    r = subprocess.run(["git", *args], cwd=config.REPO, input=stdin,
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

def blob_hash(rel: str) -> Optional[str]:
    """Same hash Mnemolith stores (`git hash-object`), so uncommitted edits count."""
    p = safe_path(rel)
    if not p or not p.is_file():
        return None
    out = _git("hash-object", str(p))
    return out.strip() if out else None

def diff_head(rel: str) -> str:
    return _git("diff", "HEAD", "--", rel) or ""

def log(rel: str, n: int = 5) -> str:
    return _git("log", f"-{n}", "--oneline", "--", rel) or ""

def find_rename(rel: str, old_hash: Optional[str]) -> Optional[str]:
    """Where did a missing file go? Returns the new repo-relative path, or None.

    1. Exact match: some other file now has the saved content (same blob hash).
    2. Git's own rename detection (handles moved-and-edited files that are tracked/staged).
    Untracked-and-edited moves can't be detected; those stay "deleted".
    """
    if old_hash:
        tracked = _git("ls-files", "-s") or ""
        for line in tracked.splitlines():
            meta, _, path = line.partition("\t")
            parts = meta.split()
            if len(parts) >= 2 and parts[1] == old_hash and path != rel \
                    and safe_path(path) and safe_path(path).is_file():
                return path
        untracked = (_git("ls-files", "-o", "--exclude-standard") or "").splitlines()
        if untracked:
            hashes = (_git("hash-object", "--stdin-paths", stdin="\n".join(untracked) + "\n")
                      or "").split()
            for path, h in zip(untracked, hashes):
                if h == old_hash:
                    return path
    status = _git("diff", "HEAD", "-M40%", "--name-status") or ""
    for line in status.splitlines():
        cols = line.split("\t")
        if len(cols) == 3 and cols[0].startswith("R") and cols[1] == rel:
            return cols[2]
    return None
