import difflib
from . import config, gitutil
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