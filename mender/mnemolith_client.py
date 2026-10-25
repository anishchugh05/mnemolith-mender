import asyncio, re
from typing import Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from .models import FileLink, StaleMemory

def list_stale() -> list[StaleMemory]:
    """All currently stale memories, via Mnemolith's Python API."""
    from mnemolith import server   # imported lazily; verify against 0.2.2
    project = server.project_name()
    root = server.repo_root()
    server.check_staleness(project, root)
    out = []
    for mid, status, files, text in server.run("MEM.LIST", project):
        if status != "stale":
            continue
        links = []
        for f in str(files).split(","):
            if "@" in f:
                path, h = f.rsplit("@", 1)
                links.append(FileLink(path=path.strip(), old_hash=h.strip() or None))
        out.append(StaleMemory(id=mid, text=text,
                               reason=server.status_reason(mid), files=links))
    return out

async def _call(tool: str, args: dict) -> str:
    params = StdioServerParameters(command="mnemolith", args=["serve"])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool(tool, args)
            return "".join(getattr(c, "text", "") for c in res.content)

def call_tool(tool: str, args: dict) -> str:
    return asyncio.run(_call(tool, args))

def apply_replace(old_id: str, new_text: str, files: list[str]) -> str:
    """Approve a draft: remember() the new fact, then replace_memory()."""
    saved = call_tool("remember", {"fact": new_text, "files": files})
    m = re.search(r"(?:Saved as|Already known as)\s+(m\d+)", saved)
    if not m:
        raise RuntimeError(f"Unexpected remember() reply: {saved}")
    return call_tool("replace_memory", {"old_id": old_id, "new_id": m.group(1)})

def apply_confirm(memory_id: str) -> str:
    return call_tool("confirm_memory", {"memory_id": memory_id})