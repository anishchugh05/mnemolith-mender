import contextlib
from . import config, queue, stats
from .drafter import draft
from .mnemolith_client import list_stale
from .models import QueueItem
from .payload import all_gone, build, current_paths, diff_text, hashes
from .triage import triage

try:
    import fcntl
except ImportError:  # non-POSIX: run without the lock
    fcntl = None

@contextlib.contextmanager
def _lock():
    """Only one pipeline run at a time (a git hook and `watch` can overlap)."""
    config.STATE_DIR.mkdir(exist_ok=True)
    if fcntl is None:
        yield True
        return
    f = open(config.STATE_DIR / "run.lock", "w")
    try:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        yield True
    finally:
        f.close()

def new_counts() -> dict:
    return {"stale": 0, "skipped": 0, "harmless": 0, "drafted": 0,
            "still_true": 0, "manual": 0, "errors": 0, "busy": 0, "last_error": ""}

def run(force: bool = False) -> dict:
    """stale memories -> triage (Nano) -> draft (Ultra) -> pending queue."""
    counts = new_counts()
    with _lock() as ok:
        if not ok:
            counts["busy"] = 1
            return counts
        existing = {} if force else {i.memory_id: i for i in queue.load()
                                     if i.status in ("pending", "rejected")}
        stale = list_stale()
        still = {m.id for m in stale}
        for it in queue.pending():  # handled elsewhere since it was queued: drop it
            if it.memory_id not in still:
                queue.set_status(it.memory_id, "obsolete")
        for mem in stale:
            counts["stale"] += 1
            p = build(mem)
            hs = hashes(p)
            prev = existing.get(mem.id)
            # Same files as when we last looked: nothing new to decide. If a file changed
            # again, the old draft is out of date, so it gets re-drafted below.
            if prev and prev.file_hashes == hs:
                counts["skipped"] += 1
                continue
            files = current_paths(p)
            diff = "\n\n".join(diff_text(c) for c in p.changes)

            def item(kind, why, d=None):
                return QueueItem(memory_id=mem.id, kind=kind, old_text=mem.text,
                                 files=files, triage_why=why, draft=d, diff=diff,
                                 file_hashes=hs)

            if all_gone(p):
                queue.add(item("manual", "all linked files were deleted"))
                counts["manual"] += 1
                continue

            try:
                t = triage(p)
                if not t.invalidated:
                    queue.add(item("confirm", t.why))
                    counts["harmless"] += 1
                    continue
                d = draft(p)
            except Exception as e:  # network, credits, rate limit: leave it for the next run
                counts["errors"] += 1
                counts["last_error"] = f"{mem.id}: {e}"
                continue

            if d is None:
                queue.add(item("manual", "drafter returned nothing: " + t.why))
                counts["manual"] += 1
            elif d.new_text.strip() == mem.text.strip():
                # Ultra checked the evidence and says the memory is still true.
                queue.add(item("confirm", "Ultra checked: still true. " + d.reason))
                counts["still_true"] += 1
            else:
                queue.add(item("replace", t.why, d))
                counts["drafted"] += 1
    stats.record_run(counts)
    return counts
