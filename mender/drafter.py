import json
from typing import Optional
from . import config, llm, tools
from .models import ChangePayload, Draft
from .payload import current_paths, dep_bumps, diff_text
from .prompts import DRAFT_SYSTEM, DRAFT_FALLBACK_SYSTEM

def _clamp(x) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return 0.0

def _context(p: ChangePayload) -> str:
    diffs = "\n\n".join(diff_text(c) for c in p.changes)
    bumps = [b for c in p.changes for b in dep_bumps(c)]
    hint = (f"\n\nDEPENDENCY VERSION CHANGES DETECTED: {'; '.join(bumps)}\n"
            "Use tavily_search to find what changed in these releases (breaking "
            "changes, new defaults) and include it in the memory if it matters."
            if bumps else "")
    moved = [f"{c.path} was moved to {c.renamed_to}" for c in p.changes if c.renamed_to]
    note = ("\nRENAMES DETECTED: " + "; ".join(moved) +
            "\nA moved file is not a deleted file: update the path, do not say it no longer applies."
            if moved else "")
    return (f"MEMORY {p.memory.id}: {p.memory.text}\n"
            f"FLAGGED BECAUSE: {p.memory.reason}\n"
            f"LINKED FILES (as saved): {', '.join(l.path for l in p.memory.files)}\n"
            f"FILES NOW AT: {', '.join(current_paths(p)) or '(none)'}{note}\n\n"
            f"CHANGES:\n{diffs}{hint}")

def _to_draft(d: dict) -> Draft:
    return Draft(new_text=str(d["new_text"]).strip(),
                 reason=str(d.get("reason", "")),
                 confidence=_clamp(d.get("confidence")))

def draft(p: ChangePayload) -> Optional[Draft]:
    """Tool-using agent loop on Ultra. Falls back to a single prompt on failure."""
    messages = [{"role": "system", "content": DRAFT_SYSTEM},
                {"role": "user", "content": _context(p)}]
    try:
        for _ in range(config.MAX_AGENT_STEPS):
            r = llm.chat("draft", config.MODEL_ULTRA, messages,
                         tools=tools.TOOLS, temperature=0.2, max_tokens=2000)
            m = r.choices[0].message
            if not m.tool_calls:
                d = llm.extract_json(m.content or "")
                if d and "new_text" in d:  # answered in text instead of calling submit_draft
                    return _to_draft(d)
                messages.append({"role": "assistant", "content": m.content or ""})
                messages.append({"role": "user",
                                 "content": "Call submit_draft with your final answer."})
                continue
            messages.append(m.model_dump(exclude_none=True))
            for tc in m.tool_calls:
                args = json.loads(tc.function.arguments or "{}")
                if tc.function.name == "submit_draft":
                    return _to_draft(args)
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": tools.run_tool(tc.function.name, args)})
    except Exception as e:
        print(f"[mender] agent loop failed ({e}); using fallback")
    return _fallback(p)

def _fallback(p: ChangePayload) -> Optional[Draft]:
    """No tool calling: we gather evidence ourselves and ask once."""
    evidence = [_context(p)]
    for link in p.memory.files:
        evidence.append(f"git log {link.path}:\n{tools.run_tool('git_log', {'path': link.path})}")
    r = llm.chat("draft-fallback", config.MODEL_ULTRA,
                 [{"role": "system", "content": DRAFT_FALLBACK_SYSTEM},
                  {"role": "user", "content": "\n\n".join(evidence)}],
                 temperature=0.2, max_tokens=2000)
    d = llm.extract_json(r.choices[0].message.content or "")
    if not d or "new_text" not in d:
        return None
    return _to_draft(d)