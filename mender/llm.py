import json, re, time
from openai import OpenAI
from . import config

_client = None

def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not config.API_KEY:
            raise RuntimeError("NEBIUS_API_KEY is not set (check your .env).")
        _client = OpenAI(base_url=config.BASE_URL, api_key=config.API_KEY)
    return _client

def chat(role: str, model: str, messages: list, tools=None, **kw):
    """Single Token Factory call. Logs model, role, tokens, latency."""
    config.STATE_DIR.mkdir(exist_ok=True)
    args = dict(model=model, messages=messages, **kw)
    if tools:
        args["tools"] = tools
    t0 = time.time()
    resp = _get_client().chat.completions.create(**args)
    u = resp.usage
    with open(config.CALL_LOG, "a") as f:
        f.write(json.dumps({
            "ts": time.time(), "role": role, "model": model,
            "prompt_tokens": getattr(u, "prompt_tokens", 0),
            "completion_tokens": getattr(u, "completion_tokens", 0),
            "latency_s": round(time.time() - t0, 3),
        }) + "\n")
    return resp

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_DECODER = json.JSONDecoder()


def extract_json(text: str):
    """The last JSON object in a model reply, ignoring <think> blocks, prose and code fences.

    Reasoning models (Nemotron) often think out loud before answering, and that text can
    contain braces of its own, so a greedy regex is not enough.
    """
    text = _THINK.sub("", text or "")
    if "<think>" in text:  # unterminated thinking (hit max_tokens): keep only what follows it, if anything
        text = text.split("</think>")[-1] if "</think>" in text else ""
    found = None
    for i, ch in enumerate(text):
        if ch == "{":
            try:
                obj, _ = _DECODER.raw_decode(text, i)
            except ValueError:
                continue
            if isinstance(obj, dict):
                found = obj
    return found
