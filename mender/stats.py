import json
from collections import defaultdict
from . import config

def summarize() -> dict:
    out = defaultdict(lambda: {"calls": 0, "prompt": 0, "completion": 0, "latency": 0.0})
    if not config.CALL_LOG.exists():
        return {}
    for line in config.CALL_LOG.read_text().splitlines():
        r = json.loads(line)
        s = out[r["model"]]
        s["calls"] += 1
        s["prompt"] += r["prompt_tokens"]
        s["completion"] += r["completion_tokens"]
        s["latency"] += r["latency_s"]
    return dict(out)