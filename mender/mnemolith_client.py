"""Mender's only door into Mnemolith. Uses Mnemolith's Python API (same machine), pointed at config.REPO."""
import os
import re

from . import config
from .models import FileLink, StaleMemory

# Point Mnemolith at the target repo, whatever folder Mender is run from.
os.environ.setdefault("MNEMOLITH_REPO", str(config.REPO))
from mnemolith import server  # noqa: E402  (must come after MNEMOLITH_REPO is set)


def project() -> str:
    return server.project_name()


def _file_driven(reason: str) -> bool:
    """Stale because a linked file changed or was deleted (not marked outdated by hand)."""
    return server.FILE_CHANGE in reason or reason.rstrip(". ").endswith("was deleted")


def list_stale() -> list[StaleMemory]:
    """Memories retired because a linked file changed (not ones someone marked outdated by hand)."""
    server.check_staleness(project(), server.repo_root())  # flag anything that changed since the last check
    out = []
    for mid, _status, files, text in server.run("MEM.LIST", project(), "STATUS", "stale"):
        reason = server.status_reason(mid)
        if not _file_driven(reason):
            continue
        links = [FileLink(path=p.strip(), old_hash=h.strip() or None)
                 for p, h in (f.rsplit("@", 1) for f in files.split(",") if "@" in f)]
        out.append(StaleMemory(id=mid, text=text, reason=reason, files=links))
    return out


def apply_replace(old_id: str, new_text: str, files: list[str]) -> str:
    """Approve a draft: save the new fact linked to the current files, then retire the old one."""
    saved = server.remember(new_text, files)
    m = re.search(r"(?:Saved as|Already known as) (m\d+)", saved)
    if not m:
        raise RuntimeError(f"Mnemolith didn't save the new memory: {saved}")
    new_id = m.group(1)
    if new_id == old_id:  # the "new" text is the old fact, so it's still true
        return apply_confirm(old_id)
    return server.replace_memory(old_id, new_id)


def apply_confirm(memory_id: str) -> str:
    """The change didn't affect this fact: mark it current again, linked to today's file versions."""
    return server.confirm_memory(memory_id)
