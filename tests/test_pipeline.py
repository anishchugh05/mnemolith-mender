import json

import pytest
from conftest import reply, switch_to_mysql, tool_call

NANO_YES = '{"invalidated": true, "why": "database changed from Postgres to MySQL"}'
NANO_NO = '{"invalidated": false, "why": "only a comment changed"}'


def _seed(repo, text="Our project runs on Postgres", files=("docker-compose.yml",)):
    repo.store.remember(text, list(files))


def agent_handler(draft_text="Our project runs on MySQL", conf=0.9, triage=NANO_YES):
    """Nano answers triage; Ultra greps once, then submits."""
    def h(role, model, messages, tools):
        if role == "triage":
            return reply(triage)
        if role == "draft":
            if not any(m.get("role") == "tool" for m in messages):
                return reply(tool_calls=[tool_call("grep_repo", {"pattern": "postgres"})])
            return reply(tool_calls=[tool_call("submit_draft", {
                "new_text": draft_text, "reason": "compose now uses mysql:8", "confidence": conf})])
        raise AssertionError(role)
    return h


def test_postgres_to_mysql_end_to_end(repo, fake_llm):
    from mender import actions, pipeline, queue
    _seed(repo)
    switch_to_mysql(repo)                                    # uncommitted
    fake_llm.handler = agent_handler()
    c = pipeline.run()
    assert (c["stale"], c["drafted"], c["harmless"], c["manual"]) == (1, 1, 0, 0)
    [item] = queue.pending()
    assert item.kind == "replace" and item.draft.new_text == "Our project runs on MySQL"
    assert "+    image: mysql:8" in item.diff
    # the agent really used a tool and saw its result
    draft_calls = [x for x in fake_llm.calls if x.role == "draft"]
    assert any(m.get("role") == "tool" and "postgres" in m["content"].lower()
               for m in draft_calls[-1].messages)
    # approve -> old retired, new active and linked to the current file
    actions.approve("m1")
    assert repo.store.mem["m1"]["status"] == "superseded"
    assert repo.store.mem["m2"]["text"] == "Our project runs on MySQL"
    assert repo.store.mem["m2"]["status"] == "active"
    assert queue.pending() == []


def test_second_run_does_not_redraft_unchanged_files(repo, fake_llm):
    from mender import pipeline
    _seed(repo); switch_to_mysql(repo)
    fake_llm.handler = agent_handler()
    pipeline.run()
    n = len(fake_llm.calls)
    c = pipeline.run()
    assert c["skipped"] == 1 and len(fake_llm.calls) == n          # no new model calls


def test_file_edited_again_after_drafting_is_redrafted(repo, fake_llm):
    from mender import pipeline, queue
    _seed(repo); switch_to_mysql(repo)
    fake_llm.handler = agent_handler()
    pipeline.run()
    (repo.path / "docker-compose.yml").write_text("services:\n  db:\n    image: mariadb:11\n")
    fake_llm.handler = agent_handler(draft_text="Our project runs on MariaDB")
    c = pipeline.run()
    assert c["skipped"] == 0 and c["drafted"] == 1
    [item] = queue.pending()                                       # old pending draft was replaced
    assert item.draft.new_text == "Our project runs on MariaDB"


def test_rejected_draft_is_not_redrafted_until_files_change(repo, fake_llm):
    from mender import actions, pipeline
    _seed(repo); switch_to_mysql(repo)
    fake_llm.handler = agent_handler()
    pipeline.run()
    actions.reject("m1")
    assert pipeline.run()["skipped"] == 1
    assert pipeline.run(force=True)["drafted"] == 1


def test_harmless_change_triaged_by_nano_only(repo, fake_llm):
    from mender import actions, pipeline, queue
    _seed(repo)
    (repo.path / "docker-compose.yml").write_text("# db\nservices:\n  db:\n    image: postgres:16\n")
    fake_llm.handler = agent_handler(triage=NANO_NO)
    c = pipeline.run()
    assert c["harmless"] == 1 and c["drafted"] == 0
    assert {x.role for x in fake_llm.calls} == {"triage"}           # Ultra never called
    [item] = queue.pending()
    assert item.kind == "confirm"
    actions.approve("m1")
    assert repo.store.mem["m1"]["status"] == "active"              # confirmed, not replaced


def test_ultra_concluding_still_true_becomes_a_confirm(repo, fake_llm):
    from mender import pipeline, queue
    _seed(repo); switch_to_mysql(repo)
    fake_llm.handler = agent_handler(draft_text="Our project runs on Postgres")
    c = pipeline.run()
    assert c["still_true"] == 1 and c["drafted"] == 0
    assert queue.pending()[0].kind == "confirm"


def test_all_files_deleted_goes_to_manual_without_any_model_call(repo, fake_llm):
    from mender import pipeline, queue
    _seed(repo)
    (repo.path / "docker-compose.yml").unlink()
    fake_llm.handler = lambda *a: (_ for _ in ()).throw(AssertionError("no model call expected"))
    c = pipeline.run()
    assert c["manual"] == 1 and fake_llm.calls == []
    assert queue.pending()[0].kind == "manual"


def test_renamed_file_is_told_to_the_drafter_not_treated_as_deleted(repo, fake_llm):
    from mender import pipeline, queue
    _seed(repo)
    (repo.path / "docker-compose.yml").rename(repo.path / "compose.yaml")
    fake_llm.handler = agent_handler(draft_text="Our project runs on Postgres (compose.yaml)", conf=0.8)
    c = pipeline.run()
    assert c["manual"] == 0 and c["drafted"] == 1
    first = next(x for x in fake_llm.calls if x.role == "draft")
    ctx = first.messages[1]["content"]
    assert "RENAMES DETECTED" in ctx and "compose.yaml" in ctx and "FILES NOW AT: compose.yaml" in ctx
    assert queue.pending()[0].files == ["compose.yaml"]             # new memory links to the new path


def test_multi_file_memory_where_only_one_file_changed(repo, fake_llm):
    from mender import pipeline
    _seed(repo, text="Postgres is the database (compose + README)",
          files=("docker-compose.yml", "README.md"))
    switch_to_mysql(repo)
    fake_llm.handler = agent_handler()
    pipeline.run()
    ctx = next(x for x in fake_llm.calls if x.role == "triage").messages[1]["content"]
    assert "README.md: unchanged since the memory was saved" in ctx
    assert "+    image: mysql:8" in ctx


def test_llm_failure_is_not_queued_and_is_retried(repo, fake_llm):
    from mender import pipeline, queue
    _seed(repo); switch_to_mysql(repo)
    def boom(*a): raise RuntimeError("402 insufficient credits")
    fake_llm.handler = boom
    c = pipeline.run()
    assert c["errors"] == 1 and "insufficient credits" in c["last_error"] and queue.load() == []
    fake_llm.handler = agent_handler()
    assert pipeline.run()["drafted"] == 1


def test_agent_failure_falls_back_to_single_prompt(repo, fake_llm):
    from mender import pipeline, queue
    _seed(repo); switch_to_mysql(repo)
    def h(role, model, messages, tools):
        if role == "triage": return reply(NANO_YES)
        if tools: raise RuntimeError("tools not supported on this model")
        return reply('Sure: {"new_text": "Our project runs on MySQL", "reason": "r", "confidence": 0.7}')
    fake_llm.handler = h
    assert pipeline.run()["drafted"] == 1
    assert queue.pending()[0].draft.confidence == 0.7


def test_concurrent_run_is_skipped(repo, fake_llm):
    import fcntl
    from mender import config, pipeline
    _seed(repo); switch_to_mysql(repo)
    config.STATE_DIR.mkdir(exist_ok=True)
    with open(config.STATE_DIR / "run.lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        assert pipeline.run()["busy"] == 1
    fake_llm.handler = agent_handler()
    assert pipeline.run()["busy"] == 0


def test_routing_stats_are_recorded(repo, fake_llm):
    from mender import pipeline, stats
    _seed(repo, "A"); repo.store.remember("B", ["README.md"])
    switch_to_mysql(repo)
    (repo.path / "README.md").write_text("# demo\nUses Postgres. (typo fix)\n")
    def h(role, model, messages, tools):
        if role == "triage":
            return reply(NANO_YES if "MEMORY m1" in messages[1]["content"] else NANO_NO)
        return agent_handler()(role, model, messages, tools)
    fake_llm.handler = h
    pipeline.run()
    r = stats.routing()
    assert r["harmless"] == 1 and r["drafted"] == 1
