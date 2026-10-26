from conftest import switch_to_mysql


def _queue_draft(repo, mid="m1", text="Our project runs on MySQL", conf=0.9):
    from mender import gitutil, queue
    from mender.models import Draft, QueueItem
    queue.add(QueueItem(mid, "replace", "Our project runs on Postgres", ["docker-compose.yml"], "why",
                        Draft(text, "compose now uses mysql:8", conf), "-a\n+b",
                        file_hashes={"docker-compose.yml": gitutil.blob_hash("docker-compose.yml")}))


def _run_review(inp):
    from typer.testing import CliRunner
    from mender.cli import app
    return CliRunner().invoke(app, ["review"], input=inp)


def test_terminal_review_approve(repo):
    from mender import queue
    repo.store.remember("Our project runs on Postgres", ["docker-compose.yml"])
    switch_to_mysql(repo)
    _queue_draft(repo)
    res = _run_review("a\n")
    assert res.exit_code == 0, res.output
    assert "Our project runs on MySQL" in res.output and "retired" in res.output
    assert repo.store.mem["m1"]["status"] == "superseded" and queue.pending() == []


def test_terminal_review_edit_then_reject_and_skip(repo):
    from mender import queue
    repo.store.remember("Our project runs on Postgres", ["docker-compose.yml"])
    switch_to_mysql(repo)
    _queue_draft(repo)
    assert queue.pending()
    _run_review("s\n")                                   # skip keeps it pending
    assert len(queue.pending()) == 1
    _run_review("r\n")                                   # reject clears it, nothing written
    assert queue.pending() == [] and repo.store.n == 1


def test_terminal_review_skips_drifted_draft(repo):
    from mender import queue
    repo.store.remember("Our project runs on Postgres", ["docker-compose.yml"])
    switch_to_mysql(repo)
    _queue_draft(repo)
    (repo.path / "docker-compose.yml").write_text("again\n")
    res = _run_review("")
    assert "files changed since this was drafted" in res.output
    assert repo.store.n == 1 and len(queue.pending()) == 1


def test_batch_confirm_of_harmless_items(repo):
    from mender import gitutil, queue
    from mender.models import QueueItem
    repo.store.remember("A", ["docker-compose.yml"])
    repo.store.remember("B", ["README.md"])
    for mid, f in (("m1", "docker-compose.yml"), ("m2", "README.md")):
        queue.add(QueueItem(mid, "confirm", "x", [f], "unrelated", None, "",
                            file_hashes={f: gitutil.blob_hash(f)}))
    res = _run_review("y\n")
    assert "Mark them all still true" in res.output and queue.pending() == []
