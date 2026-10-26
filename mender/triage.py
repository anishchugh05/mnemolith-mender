import json, re
from . import config, llm
from .models import ChangePayload, TriageResult
from .payload import all_gone, diff_text
from .prompts import TRIAGE_SYSTEM

def _parse(text: str) -> TriageResult:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            d = json.loads(m.group(0))
            return TriageResult(bool(d["invalidated"]), str(d.get("why", "")))
        except (ValueError, KeyError):
            pass
    return TriageResult(True, "triage output unparseable, escalating")

def triage(p: ChangePayload) -> TriageResult:
    if all_gone(p):
        return TriageResult(True, "all linked files were deleted")
    diffs = "\n\n".join(diff_text(c) for c in p.changes)
    user = (f"MEMORY {p.memory.id}: {p.memory.text}\n"
            f"FLAGGED BECAUSE: {p.memory.reason}\n\nCHANGES:\n{diffs}")
    r = llm.chat("triage", config.MODEL_NANO,
                 [{"role": "system", "content": TRIAGE_SYSTEM},
                  {"role": "user", "content": user}],
                 temperature=0, max_tokens=1500)
    return _parse(r.choices[0].message.content or "")