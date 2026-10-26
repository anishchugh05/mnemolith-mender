import difflib
import re
from . import config, gitutil
from .models import ChangePayload, FileChange, StaleMemory

def build(mem: StaleMemory) -> ChangePayload:
    changes = []
    for link in mem.files:
        new = gitutil.working(link.path)
        old = gitutil.blob(link.old_hash)
        deleted, renamed_to = new is None, None
        if deleted:
            renamed_to = gitutil.find_rename(link.path, link.old_hash)
            if renamed_to:
                new, deleted = gitutil.working(renamed_to), False
        changed = deleted or renamed_to is not None or gitutil.blob_hash(link.path) != link.old_hash
        changes.append(FileChange(path=link.path, old=old, new=new, deleted=deleted,
                                  renamed_to=renamed_to, changed=changed))
    return ChangePayload(memory=mem, changes=changes)

def current_paths(p: ChangePayload) -> list[str]:
    """Where the linked files live now (renamed files at their new path; deleted ones dropped)."""
    return [c.renamed_to or c.path for c in p.changes if not c.deleted]

def hashes(p: ChangePayload) -> dict:
    """Current blob hashes for every path the drafting decision depends on."""
    out = {}
    for c in p.changes:
        out[c.path] = gitutil.blob_hash(c.path)
        if c.renamed_to:
            out[c.renamed_to] = gitutil.blob_hash(c.renamed_to)
    return out

def all_gone(p: ChangePayload) -> bool:
    """True when every linked file was deleted outright (no rename found)."""
    return bool(p.changes) and all(c.deleted for c in p.changes)

def diff_text(c: FileChange) -> str:
    if c.deleted or c.new is None:
        return f"{c.path}: FILE DELETED"
    head = f"{c.path} -> {c.renamed_to} (RENAMED)\n" if c.renamed_to else ""
    if not c.changed:
        return f"{c.path}: unchanged since the memory was saved"
    if c.old is None:
        return (f"{head}{c.path}: (old version unavailable)\n"
                f"--- current ---\n{c.new[:config.MAX_FILE_CHARS]}")
    d = list(difflib.unified_diff(c.old.splitlines(), c.new.splitlines(),
                                  f"a/{c.path}", f"b/{c.renamed_to or c.path}", lineterm=""))
    if not d:
        return f"{head}(content unchanged)".strip()
    return (head + "\n".join(d))[:config.MAX_FILE_CHARS]

DEP_FILES = ("package.json", "requirements.txt", "pyproject.toml",
             "go.mod", "Cargo.toml", "Gemfile", "pom.xml")

_REQ = re.compile(r'^\s*([A-Za-z0-9_.\-]+)\s*(?:==|~=|>=|<=|>|<)\s*([0-9][\w.\-]*)', re.M)
_QUOTED = re.compile(r'"([A-Za-z0-9_.\-]+)\s*(?:==|~=|>=|<=|>|<)\s*([0-9][\w.\-]*)"')
_PKG = re.compile(r'"([@\w./\-]+)"\s*:\s*"[\^~>=<\s]*([0-9][\w.\-]*)"')

def is_dependency_file(path: str) -> bool:
    return path.rsplit("/", 1)[-1] in DEP_FILES

def _versions(text: str) -> dict:
    found = {}
    for rx in (_REQ, _QUOTED, _PKG):
        for name, ver in rx.findall(text or ""):
            if name != "version":
                found[name] = ver
    return found

def dep_bumps(c: FileChange) -> list[str]:
    """Best-effort: 'next 14.2.0 -> 15.0.0' style changes in dependency files."""
    if not is_dependency_file(c.renamed_to or c.path) or c.old is None or c.new is None:
        return []
    old, new = _versions(c.old), _versions(c.new)
    return [f"{n} {old[n]} -> {new[n]}" for n in new if n in old and old[n] != new[n]]
