from dataclasses import dataclass, field
from typing import Literal, Optional

@dataclass
class FileLink:
    path: str                    # repo-relative
    old_hash: Optional[str]      # git blob sha1 saved with the memory

@dataclass
class StaleMemory:
    id: str
    text: str
    reason: str
    files: list[FileLink] = field(default_factory=list)

@dataclass
class FileChange:
    path: str
    old: Optional[str]           # None if old version isn't in git
    new: Optional[str]           # None if file was deleted
    deleted: bool = False

@dataclass
class ChangePayload:
    memory: StaleMemory
    changes: list[FileChange]

@dataclass
class TriageResult:
    invalidated: bool
    why: str

@dataclass
class Draft:
    new_text: str
    reason: str
    confidence: float            # model-reported, not calibrated

@dataclass
class QueueItem:
    memory_id: str
    kind: Literal["replace", "confirm", "manual"]
    old_text: str
    files: list[str]
    triage_why: str
    draft: Optional[Draft] = None
    diff: str = ""
    status: Literal["pending", "approved", "rejected"] = "pending"