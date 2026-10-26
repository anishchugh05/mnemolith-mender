"""Approve / reject, shared by the terminal review and the web UI.

Every write to Mnemolith goes through approve(), which refuses to save a draft
whose underlying files changed after it was drafted.
"""
from . import queue


class Drifted(Exception):
    """The files changed since this draft was made; it must be re-drafted."""


def approve(memory_id: str, text: str | None = None) -> str:
    it = queue.get_pending(memory_id)
    if it is None:
        raise LookupError(f"{memory_id} is not pending")
    if it.kind == "manual":
        raise ValueError(f"{memory_id} needs a manual decision (nothing to approve)")
    if queue.drifted(it):
        raise Drifted(f"{memory_id}: files changed since this was drafted. "
                      "Run `mender run` to re-draft.")
    # Imported here so importing this module never needs Mnemolith/Java.
    from .mnemolith_client import apply_confirm, apply_replace, status
    now = status(memory_id)
    if now != "stale":  # someone (or an AI tool) already confirmed, replaced or removed it
        queue.set_status(memory_id, "obsolete")
        raise LookupError(f"{memory_id} was already handled elsewhere (it's {now or 'gone'} now); "
                          "dropped it from the queue.")
    if it.kind == "replace":
        new_text = (text if text is not None else it.draft.new_text).strip()
        if not new_text:
            raise ValueError("memory text can't be empty")
        msg = apply_replace(it.memory_id, new_text, it.files)
    else:
        msg = apply_confirm(it.memory_id)
    queue.set_status(memory_id, "approved")
    return msg


def reject(memory_id: str) -> None:
    if queue.get_pending(memory_id) is None:
        raise LookupError(f"{memory_id} is not pending")
    queue.set_status(memory_id, "rejected")
