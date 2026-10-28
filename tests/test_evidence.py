def test_tavily_evidence_has_sources(repo):
    from mender import tools
    out = ("redis-py 5.0.0 release: Dropped Python 3.7 support. (https://github.com/redis/redis-py/releases/tag/v5.0.0)\n"
           "Other page: nothing useful (https://example.com/x)")
    ev = tools.evidence("tavily_search", {"query": "redis-py 5.0.0 release notes"}, out)
    assert ev["arg"] == "redis-py 5.0.0 release notes"
    assert [s["url"] for s in ev["sources"]] == [
        "https://github.com/redis/redis-py/releases/tag/v5.0.0", "https://example.com/x"]
    assert ev["summary"] == "2 web results"
    assert ev["sources"][0]["snippet"].startswith("Dropped Python 3.7")


def test_grep_evidence_counts_matches(repo):
    from mender import tools
    assert tools.evidence("grep_repo", {"pattern": "mysql"}, "no matches")["summary"] == "no matches"
    assert tools.evidence("grep_repo", {"pattern": "mysql"}, "a:1:x\nb:2:y")["summary"] == "2 matching lines"


def test_evidence_survives_queue_roundtrip(repo):
    from mender import queue
    from mender.models import Draft, QueueItem
    ev = [{"tool": "tavily_search", "arg": "q", "summary": "1 web results",
           "sources": [{"title": "t", "url": "https://e.com"}]}]
    queue.add(QueueItem(memory_id="m9", kind="replace", old_text="a", files=["f"],
                        triage_why="w", draft=Draft("b", "r", 0.9, ev)))
    assert queue.get_pending("m9").draft.evidence == ev


def test_old_queue_without_evidence_still_loads(repo):
    import json
    from mender import config, queue
    config.STATE_DIR.mkdir(exist_ok=True)
    config.QUEUE_FILE.write_text(json.dumps([{
        "memory_id": "m1", "kind": "replace", "old_text": "a", "files": [], "triage_why": "w",
        "draft": {"new_text": "b", "reason": "r", "confidence": 0.5}, "diff": "",
        "status": "pending", "file_hashes": {}}]))
    assert queue.get_pending("m1").draft.evidence == []


def _bump_payload(repo):
    from mender.models import ChangePayload, FileChange, StaleMemory
    ch = FileChange("requirements.txt", "redis==4.5.0\n", "redis==5.0.0\n")
    return ChangePayload(StaleMemory("m1", "pin redis 4.5.0", "r", []), [ch])


def test_invented_quote_is_flagged(repo):
    from mender import drafter
    p = _bump_payload(repo)
    out = ["Blog: Redis 5.0.0 adds sentinel ssl. (https://e.com/a)"]
    bad = {"reason": 'It says "socket_timeout now defaults to 5 seconds everywhere"', "new_text": "x"}
    ok = {"reason": 'It says "Redis 5.0.0 adds sentinel ssl"', "new_text": "x"}
    assert any("quoted" in w for w in drafter._grounding(p, bad, out))
    assert drafter._grounding(p, ok, out) == []


def test_version_missing_from_sources_is_flagged(repo):
    from mender import drafter
    p = _bump_payload(repo)
    w = drafter._grounding(p, {"reason": "r", "new_text": "t"},
                           ["Old post about 4.x (https://e.com/old)"])
    assert any("5.0.0" in x for x in w)


def test_agent_gets_one_retry_then_draft_is_capped(repo, fake_llm):
    from conftest import reply, tool_call
    from mender import drafter
    p = _bump_payload(repo)
    seen = {"n": 0}

    def h(role, model, messages, tools):
        seen["n"] += 1
        if seen["n"] == 1:
            return reply(tool_calls=[tool_call("read_file", {"path": "requirements.txt"})])
        return reply(tool_calls=[tool_call("submit_draft", {
            "new_text": "pin redis 5.0.0",
            "reason": 'Source states "defaults changed to ten retries and a 32 KB buffer"',
            "confidence": 0.95})])
    fake_llm.handler = h
    d = drafter.draft(p)
    assert seen["n"] == 3                       # read_file, rejected submit, resubmit
    assert d.warnings and d.confidence <= 0.5


def test_markdown_and_linebreaks_do_not_cause_false_flags(repo):
    from mender import drafter
    p = _bump_payload(repo)
    out = ["Releases: Default connection settings were updated: `socket_timeout` and "
           "`socket_connect_timeout` now default to 5 seconds, TCP keepalive is enabled (https://e.com/r) 5.0.0"]
    d = {"reason": 'It states "Default connection settings were updated: socket_timeout and '
                   'socket_connect_timeout now default to 5 seconds"', "new_text": "x"}
    assert drafter._grounding(p, d, out) == []


def test_tavily_multiline_content_is_one_line(repo, monkeypatch):
    import sys, types
    from mender import config, tools
    monkeypatch.setattr(config, "TAVILY_KEY", "k")
    fake = types.ModuleType("tavily")
    class C:
        def __init__(self, api_key): pass
        def search(self, q, max_results=3):
            return {"results": [{"title": "T", "content": "line one\n\n- bullet two", "url": "https://e.com/p"}]}
    fake.TavilyClient = C
    monkeypatch.setitem(sys.modules, "tavily", fake)
    out = tools.run_tool("tavily_search", {"query": "q"})
    assert "\n" not in out
    ev = tools.evidence("tavily_search", {"query": "q"}, out)
    assert ev["sources"][0]["url"] == "https://e.com/p"
