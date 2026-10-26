import json, subprocess
from . import config, gitutil

TOOLS = [
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a repo file (current version).",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"}},
                       "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "git_log",
        "description": "Recent commits touching a file.",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"}},
                       "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "grep_repo",
        "description": "Case-insensitive search of tracked repo files for a literal string. Returns matching lines.",
        "parameters": {"type": "object",
                       "properties": {"pattern": {"type": "string"}},
                       "required": ["pattern"]}}},
    {"type": "function", "function": {
        "name": "tavily_search",
        "description": "Web search, for release notes on a dependency or library version change.",
        "parameters": {"type": "object",
                       "properties": {"query": {"type": "string"}},
                       "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "submit_draft",
        "description": "Submit the final corrected memory. Call exactly once.",
        "parameters": {"type": "object",
                       "properties": {"new_text": {"type": "string"},
                                      "reason": {"type": "string"},
                                      "confidence": {"type": "number"}},
                       "required": ["new_text", "reason", "confidence"]}}},
]

def _grep(pattern: str) -> str:
    r = subprocess.run(["git", "grep", "-n", "-I", "-i", "-F", "--", pattern],
                       cwd=config.REPO, capture_output=True, text=True)
    lines = r.stdout.splitlines()
    if not lines:
        return "no matches"
    out = "\n".join(lines[:40])
    return out + (f"\n... {len(lines) - 40} more" if len(lines) > 40 else "")

def _tavily(query: str) -> str:
    if not config.TAVILY_KEY:
        return "web search unavailable (no TAVILY_API_KEY)"
    from tavily import TavilyClient
    res = TavilyClient(api_key=config.TAVILY_KEY).search(query, max_results=3)
    return "\n".join(f"{x['title']}: {x['content'][:400]} ({x['url']})"
                     for x in res.get("results", []))

def run_tool(name: str, args: dict) -> str:
    """Read-only tools, confined to the repo."""
    try:
        if name == "read_file":
            txt = gitutil.working(args["path"])
            return txt[:config.MAX_FILE_CHARS] if txt is not None else "file not found"
        if name == "git_log":
            return gitutil.log(args["path"]) or "no history"
        if name == "grep_repo":
            return _grep(args["pattern"])
        if name == "tavily_search":
            return _tavily(args["query"])
    except Exception as e:  # tools must never crash the agent loop
        return f"tool error: {e}"
    return f"unknown tool: {name}"