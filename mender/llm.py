import json, time
from openai import OpenAI
from . import config

_client = OpenAI(base_url=config.BASE_URL, api_key=config.API_KEY)

def chat(role: str, model: str, messages: list, tools=None, **kw):
    """Single Token Factory call. Logs model, role, tokens, latency."""
    config.STATE_DIR.mkdir(exist_ok=True)
    args = dict(model=model, messages=messages, **kw)
    if tools:
        args["tools"] = tools
    t0 = time.time()
    resp = _client.chat.completions.create(**args)
    u = resp.usage
    with open(config.CALL_LOG, "a") as f:
        f.write(json.dumps({
            "ts": time.time(), "role": role, "model": model,
            "prompt_tokens": getattr(u, "prompt_tokens", 0),
            "completion_tokens": getattr(u, "completion_tokens", 0),
            "latency_s": round(time.time() - t0, 3),
        }) + "\n")
    return resp