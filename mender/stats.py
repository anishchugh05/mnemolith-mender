import json
import time
from collections import defaultdict
from . import config

RUNS_LOG = config.STATE_DIR / "runs.jsonl"

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

def record_run(counts: dict) -> None:
    """One line per pipeline run, so the routing numbers in the README/demo are measured."""
    if not any(counts.get(k) for k in ("harmless", "drafted", "manual")):
        return  # nothing new happened (e.g. watch polling)
    config.STATE_DIR.mkdir(exist_ok=True)
    with open(RUNS_LOG, "a") as f:
        f.write(json.dumps({"ts": time.time(), **counts}) + "\n")

def routing() -> dict:
    """Totals across runs: how many stale memories each model tier handled."""
    tot = {"stale": 0, "harmless": 0, "drafted": 0, "still_true": 0, "manual": 0}
    if not RUNS_LOG.exists():
        return tot
    for line in RUNS_LOG.read_text().splitlines():
        r = json.loads(line)
        for k in tot:
            tot[k] += r.get(k, 0)
    return tot
