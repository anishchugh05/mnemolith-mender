import json
from dataclasses import asdict
from . import config
from .models import Draft, QueueItem

def load() -> list[QueueItem]:
    if not config.QUEUE_FILE.exists():
        return []
    out = []
    for d in json.loads(config.QUEUE_FILE.read_text()):
        dr = d.pop("draft", None)
        out.append(QueueItem(draft=Draft(**dr) if dr else None, **d))
    return out

def save(items: list[QueueItem]) -> None:
    config.STATE_DIR.mkdir(exist_ok=True)
    config.QUEUE_FILE.write_text(json.dumps([asdict(i) for i in items], indent=2))

def add(item: QueueItem) -> None:
    items = [i for i in load()
             if not (i.memory_id == item.memory_id and i.status == "pending")]
    items.append(item)
    save(items)

def pending() -> list[QueueItem]:
    """Lowest confidence first; manual items (no draft) come first of all."""
    def key(i: QueueItem):
        if i.kind == "manual": return -1.0
        if i.kind == "confirm" or not i.draft: return 2.0
        return i.draft.confidence
    return sorted((i for i in load() if i.status == "pending"), key=key)

def set_status(memory_id: str, status: str) -> None:
    items = load()
    for i in items:
        if i.memory_id == memory_id and i.status == "pending":
            i.status = status
    save(items)