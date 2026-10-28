import json, re
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
            "Use tavily_search to find what changed in these releases. Keep the memory to "
            "ONE short sentence. Mention a release detail only if a search result names that exact "
            "version and states it word for word; otherwise just say it is a major release whose defaults may "
            "have changed. Never write numbers you did not see in a result."
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

def _norm(s: str) -> str:
    s = re.sub(r"[`*_#>]|(?<=\s)-(?=\s)", " ", s.lower())   # markdown noise
    return re.sub(r"\s+", " ", s).strip()

def _grounding(p: ChangePayload, d: dict, outputs: list) -> list:
    """Check the draft against what the tools really returned. Never trusts the model's word.

    1. Any quoted passage in the reason or text must appear in a tool result.
    2. For a dependency bump, a web result must name the new version.
    """
    corpus = _norm("\n".join(outputs))
    warnings = []
    said = f"{d.get('reason', '')} {d.get('new_text', '')}"
    for q in re.findall(r'["\u201c]([^"\u201d]{20,})["\u201d]', said):
        pieces = [x for x in re.split(r"\.\.\.|\u2026", q) if len(x.strip()) >= 12]
        if any(_norm(x) not in corpus for x in pieces):
            warnings.append("A passage quoted in the reason does not appear in any source "
                            "the agent looked at.")
            break
    web = _norm("\n".join(o for o in outputs if "http" in o))
    for c in p.changes:
        for b in dep_bumps(c):
            name, _, new = b.rpartition(" -> ")
            ver = new.strip()
            if web and ver and ver.lower() not in web:
                warnings.append(f"No search result mentions version {ver}; "
                                "release details are unverified.")
    return warnings

def _to_draft(d: dict, evidence=None, warnings=None) -> Draft:
    conf = _clamp(d.get("confidence"))
    if warnings:
        conf = min(conf, 0.5)       # an unverified claim must not look confident
    return Draft(new_text=str(d["new_text"]).strip(),
                 reason=str(d.get("reason", "")),
                 confidence=conf,
                 evidence=list(evidence or []),
                 warnings=list(warnings or []))

def draft(p: ChangePayload) -> Optional[Draft]:
    """Tool-using agent loop on Ultra. Falls back to a single prompt on failure."""
    messages = [{"role": "system", "content": DRAFT_SYSTEM},
                {"role": "user", "content": _context(p)}]
    evidence: list = []
    outputs: list = []
    retried = False
    try:
        for _ in range(config.MAX_AGENT_STEPS):
            r = llm.chat("draft", config.MODEL_ULTRA, messages,
                         tools=tools.TOOLS, temperature=0.2, max_tokens=2000)
            m = r.choices[0].message
            if not m.tool_calls:
                d = llm.extract_json(m.content or "")
                if d and "new_text" in d:  # answered in text instead of calling submit_draft
                    return _to_draft(d, evidence, _grounding(p, d, outputs))
                messages.append({"role": "assistant", "content": m.content or ""})
                messages.append({"role": "user",
                                 "content": "Call submit_draft with your final answer."})
                continue
            messages.append(m.model_dump(exclude_none=True))
            for tc in m.tool_calls:
                args = json.loads(tc.function.arguments or "{}")
                if tc.function.name == "submit_draft":
                    w = _grounding(p, args, outputs)
                    if w and not retried:      # one chance to fix unsupported claims
                        retried = True
                        messages.append({"role": "tool", "tool_call_id": tc.id, "content":
                                         "REJECTED: " + " ".join(w) + " Resubmit with submit_draft, "
                                         "keeping only details that appear in the tool results, "
                                         "with no invented quotes. If no result supports a detail, "
                                         "leave it out."})
                        continue
                    return _to_draft(args, evidence, w)
                out = tools.run_tool(tc.function.name, args)
                outputs.append(out)
                evidence.append(tools.evidence(tc.function.name, args, out))
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": out})
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