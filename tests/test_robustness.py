"""Cases found while running Mender against a real Mnemolith."""
from conftest import reply, switch_to_mysql, tool_call


def test_triage_ignores_braces_in_reasoning(repo):
    from mender.triage import _parse
    r = _parse('<think>The diff {changes the image}... so {not sure}</think>\n'
               '{"invalidated": false, "why": "only a comment changed"}')
    assert r.invalidated is False and r.why == "only a comment changed"


def test_triage_unterminated_reasoning_escalates(repo):
    from mender.triage import _parse
    assert _parse('<think>{"invalidated": false} hmm, let me reconsider').invalidated is True


def test_drafter_accepts_json_answer_given_as_text(repo, fake_llm):
    from mender import payload
    from mender.drafter import draft
    from mender.mnemolith_client import list_stale
    repo.store.remember("Our project runs on Postgres", ["docker-compose.yml"])
    switch_to_mysql(repo)
    fake_llm.handler = lambda *a: reply('Done. {"new_text": "Our project runs on MySQL 8", '
                                        '"reason": "image changed", "confidence": 0.9}')
    d = draft(payload.build(list_stale()[0]))
    assert d.new_text == "Our project runs on MySQL 8"
    assert len(fake_llm.calls) == 1  # no pointless nudging


def test_memory_handled_elsewhere_is_not_overwritten(repo, fake_llm):
    import pytest
    from mender import actions, pipeline, queue
    repo.store.remember("Our project runs on Postgres", ["docker-compose.yml"])
    switch_to_mysql(repo)
    fake_llm.handler = lambda role, *a: (
        reply('{"invalidated": true, "why": "db changed"}') if role == "triage" else
        reply(None, [tool_call("submit_draft", {"new_text": "Our project runs on MySQL 8",
                                                "reason": "x", "confidence": 0.9})]))
    pipeline.run()
    assert [i.memory_id for i in queue.pending()] == ["m1"]
    # meanwhile Claude fixed it through Mnemolith directly
    repo.store.remember("We use MySQL now", ["docker-compose.yml"])
    repo.store.replace_memory("m1", "m2")
    with pytest.raises(LookupError):
        actions.approve("m1")
    assert queue.pending() == []
    assert [m for m, v in repo.store.mem.items() if v["status"] == "active"] == ["m2"]


def test_run_drops_queue_items_resolved_elsewhere(repo, fake_llm):
    from mender import pipeline, queue
    repo.store.remember("Our project runs on Postgres", ["docker-compose.yml"])
    switch_to_mysql(repo)
    fake_llm.handler = lambda role, *a: (
        reply('{"invalidated": true, "why": "db changed"}') if role == "triage" else
        reply(None, [tool_call("submit_draft", {"new_text": "MySQL", "reason": "x", "confidence": 0.9})]))
    pipeline.run()
    repo.store.confirm_memory("m1")
    pipeline.run()
    assert queue.pending() == []


def test_unchanged_uncommitted_file_is_not_reported_as_changed(repo):
    from mender import payload
    from mender.mnemolith_client import list_stale
    (repo.path / "notes.txt").write_text("never committed\n")
    repo.store.remember("Notes and db", ["notes.txt", "docker-compose.yml"])
    switch_to_mysql(repo)
    p = payload.build(list_stale()[0])
    by_path = {c.path: c for c in p.changes}
    assert by_path["notes.txt"].changed is False
    assert by_path["docker-compose.yml"].changed is True


def test_retire_memory_whose_files_were_all_deleted(repo, fake_llm):
    import pytest
    from mender import actions, pipeline, queue
    repo.store.remember("Seed data lives in docker-compose.yml", ["docker-compose.yml"])
    (repo.path / "docker-compose.yml").unlink()
    fake_llm.handler = lambda *a: pytest.fail("no model call for a deleted file")
    pipeline.run()
    [it] = queue.pending()
    assert it.kind == "manual"
    with pytest.raises(ValueError):
        actions.approve("m1")
    actions.retire("m1")
    assert queue.pending() == []
    assert "deleted" in repo.store.mem["m1"]["reason"]
    pipeline.run()                       # retired by hand: not picked up again
    assert queue.pending() == []
