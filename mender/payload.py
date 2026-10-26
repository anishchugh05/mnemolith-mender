import difflib
from . import config, gitutil
import re
from .models import ChangePayload, FileChange, StaleMemory

def build(mem: StaleMemory) -> ChangePayload:
    changes = []
    for link in mem.files:
        new = gitutil.working(link.path)
        old = gitutil.blob(link.old_hash)
        changes.append(FileChange(path=link.path, old=old, new=new,
                                  deleted=new is None))
    return ChangePayload(memory=mem, changes=changes)

def diff_text(c: FileChange) -> str:
    if c.deleted or c.new is None:
        return f"{c.path}: FILE DELETED"
    if c.old is None:
        return (f"{c.path}: (old version unavailable)\n"
                f"--- current ---\n{c.new[:config.MAX_FILE_CHARS]}")
    d = difflib.unified_diff(c.old.splitlines(), c.new.splitlines(),
                             f"a/{c.path}", f"b/{c.path}", lineterm="")
    return "\n".join(d)[:config.MAX_FILE_CHARS]

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
    if not is_dependency_file(c.path) or c.old is None or c.new is None:
        return []
    old, new = _versions(c.old), _versions(c.new)
    return [f"{n} {old[n]} -> {new[n]}" for n in new if n in old and old[n] != new[n]]