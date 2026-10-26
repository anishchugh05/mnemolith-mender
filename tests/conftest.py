"""Test fixtures: a throwaway git repo, a fake Mnemolith store, and scripted model replies.

The fake `mnemolith.server` mirrors the Python API Mender uses (MEM.LIST tuples of
(id, status, "path@hash,...", text), status_reason, FILE_CHANGE, remember,
replace_memory, confirm_memory). It is a test double based on how Mender calls the
real module; the real thing is exercised by running Mender against a real repo.
"""
import json
import subprocess
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FILE_CHANGE = "changed since this was saved"


class FakeStore:
    def __init__(self, root: Path):
        self.root = root
        self.mem: dict[str, dict] = {}
        self.n = 0

    def _hash(self, rel: str):
        f = self.root / rel
        if not f.is_file():
            return None
        r = subprocess.run(["git", "hash-object", str(f)], cwd=self.root,
                           capture_output=True, text=True)
        return r.stdout.strip()

    def remember(self, text, files=None):
        for mid, m in self.mem.items():
            if m["text"] == text and m["status"] == "active":
                return f"Already known as {mid}."
        self.n += 1
        mid = f"m{self.n}"
        self.mem[mid] = {"text": text, "status": "active", "reason": "",
                         "files": {f: self._hash(f) for f in (files or [])}}
        return f"Saved as {mid}."

    def check_staleness(self, project, root):
        for mid, m in self.mem.items():
            if m["status"] != "active":
                continue
            for f, h in m["files"].items():
                cur = self._hash(f)
                if cur is None:
                    m["status"], m["reason"] = "stale", f"{f} was deleted"
                elif cur != h:
                    m["status"], m["reason"] = "stale", f"{f} {FILE_CHANGE}."

    def listing(self, status):
        return [(mid, m["status"],
                 ",".join(f"{f}@{h or ''}" for f, h in m["files"].items()), m["text"])
                for mid, m in self.mem.items() if m["status"] == status]

    def replace_memory(self, old, new):
        self.mem[old]["status"] = "superseded"
        self.mem[old]["reason"] = f'replaced by {new}: "{self.mem[new]["text"]}"'
        return f"{old} retired; {new} replaces it."

    def confirm_memory(self, mid):
        m = self.mem[mid]
        m["status"], m["reason"] = "active", ""
        m["files"] = {f: self._hash(f) for f in m["files"]}
        return f"{mid} confirmed."


def _install_fake_mnemolith(monkeypatch, root: Path) -> FakeStore:
    store = FakeStore(root)
    server = types.ModuleType("mnemolith.server")
    server.FILE_CHANGE = FILE_CHANGE
    server.project_name = lambda: "demo"
    server.repo_root = lambda: str(root)
    server.check_staleness = store.check_staleness
    server.run = lambda cmd, project, *a: store.listing(a[1]) if a[:1] == ("STATUS",) else []
    server.status_reason = lambda mid: store.mem[mid]["reason"]
    server.remember = store.remember
    server.replace_memory = store.replace_memory
    server.confirm_memory = store.confirm_memory
    pkg = types.ModuleType("mnemolith")
    pkg.server = server
    monkeypatch.setitem(sys.modules, "mnemolith", pkg)
    monkeypatch.setitem(sys.modules, "mnemolith.server", server)
    return store


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A git repo with one committed docker-compose.yml, and Mender pointed at it."""
    r = tmp_path / "demo"
    r.mkdir()
    g = lambda *a: subprocess.run(["git", *a], cwd=r, check=True, capture_output=True)
    g("init", "-q")
    g("config", "user.email", "t@example.com")
    g("config", "user.name", "t")
    (r / "docker-compose.yml").write_text("services:\n  db:\n    image: postgres:16\n")
    (r / "README.md").write_text("# demo\nUses Postgres.\n")
    g("add", "-A")
    g("commit", "-q", "-m", "init")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MENDER_REPO", str(r))
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    for name in [n for n in sys.modules if n == "mender" or n.startswith("mender.")]:
        del sys.modules[name]          # config resolves REPO at import time
    store = _install_fake_mnemolith(monkeypatch, r)
    return SimpleNamespace(path=r, store=store, git=g)


def tool_call(name, args, id="c1"):
    return SimpleNamespace(id=id, function=SimpleNamespace(name=name, arguments=json.dumps(args)))


def reply(content=None, tool_calls=None):
    m = SimpleNamespace(content=content, tool_calls=tool_calls)

    def dump(**_):
        d = {"role": "assistant", "content": content or ""}
        if tool_calls:
            d["tool_calls"] = [{"id": t.id, "type": "function",
                                "function": {"name": t.function.name,
                                             "arguments": t.function.arguments}} for t in tool_calls]
        return d
    m.model_dump = dump
    return SimpleNamespace(choices=[SimpleNamespace(message=m)],
                           usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))


@pytest.fixture
def fake_llm(repo, monkeypatch):
    """Replace llm.chat with a scripted handler: handler(role, model, messages, tools)."""
    from mender import llm
    state = SimpleNamespace(calls=[], handler=None)

    def chat(role, model, messages, tools=None, **kw):
        state.calls.append(SimpleNamespace(role=role, model=model,
                                           messages=[dict(m) for m in messages], tools=tools))
        return state.handler(role, model, messages, tools)

    monkeypatch.setattr(llm, "chat", chat)
    return state


def switch_to_mysql(repo):
    (repo.path / "docker-compose.yml").write_text("services:\n  db:\n    image: mysql:8\n")
