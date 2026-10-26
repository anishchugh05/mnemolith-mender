from . import queue
from .drafter import draft
from .mnemolith_client import list_stale
from .models import QueueItem
from .payload import build, diff_text
from .triage import triage

def run(force: bool = False) -> dict:
    """stale memories -> triage (Nano) -> draft (Ultra) -> pending queue."""
    counts = {"stale": 0, "skipped": 0, "harmless": 0, "drafted": 0, "manual": 0}
    seen = set() if force else {i.memory_id for i in queue.load()
                                if i.status in ("pending", "rejected")}
    for mem in list_stale():
        counts["stale"] += 1
        if mem.id in seen:
            counts["skipped"] += 1
            continue
        p = build(mem)
        files = [c.path for c in p.changes if not c.deleted]
        diff = "\n\n".join(diff_text(c) for c in p.changes)

        def item(kind, why, d=None):
            return QueueItem(memory_id=mem.id, kind=kind, old_text=mem.text,
                             files=files, triage_why=why, draft=d, diff=diff)

        if p.changes and all(c.deleted for c in p.changes):
            queue.add(item("manual", "all linked files were deleted"))
            counts["manual"] += 1
            continue

        t = triage(p)
        if not t.invalidated:
            queue.add(item("confirm", t.why))
            counts["harmless"] += 1
            continue

        d = draft(p)
        if d is None:
            queue.add(item("manual", "drafter returned nothing: " + t.why))
            counts["manual"] += 1
        else:
            queue.add(item("replace", t.why, d))
            counts["drafted"] += 1
    return counts