import pytest
from conftest import switch_to_mysql


def _item(repo, **kw):
    from mender import gitutil
    from mender.models import Draft, QueueItem
    base = dict(memory_id="m1", kind="replace", old_text="Our project runs on Postgres",
                files=["docker-compose.yml"], triage_why="x",
                draft=Draft("Our project runs on MySQL", "r", 0.9), diff="",
                file_hashes={"docker-compose.yml": gitutil.blob_hash("docker-compose.yml")})
    base.update(kw)
    return QueueItem(**base)


def test_drafted_against_old_files_cannot_be_approved(repo):
    from mender import actions, queue
    repo.store.remember("Our project runs on Postgres", ["docker-compose.yml"])
    switch_to_mysql(repo)
    queue.add(_item(repo))                                   # drafted against the MySQL version
    (repo.path / "docker-compose.yml").write_text("services:\n  db:\n    image: mariadb:11\n")
    assert queue.drifted(queue.pending()[0])
    with pytest.raises(actions.Drifted):
        actions.approve("m1")
    assert repo.store.n == 1                                 # nothing was written to Mnemolith
    assert queue.pending()                                   # still pending, not lost


def test_manual_items_cannot_be_approved(repo):
    from mender import actions, queue
    queue.add(_item(repo, kind="manual", draft=None))
    with pytest.raises(ValueError):
        actions.approve("m1")


def test_edit_replaces_text_and_empty_text_is_refused(repo):
    from mender import actions, queue
    repo.store.remember("Our project runs on Postgres", ["docker-compose.yml"])
    switch_to_mysql(repo)
    queue.add(_item(repo))
    with pytest.raises(ValueError):
        actions.approve("m1", "   ")
    actions.approve("m1", "Database is MySQL 8 (docker-compose.yml)")
    assert repo.store.mem["m2"]["text"] == "Database is MySQL 8 (docker-compose.yml)"


def test_review_order_manual_then_lowest_confidence_then_confirms(repo):
    from mender import queue
    from mender.models import Draft
    queue.add(_item(repo, memory_id="m1", draft=Draft("a", "r", 0.95)))
    queue.add(_item(repo, memory_id="m2", draft=Draft("b", "r", 0.40)))
    queue.add(_item(repo, memory_id="m3", kind="confirm", draft=None))
    queue.add(_item(repo, memory_id="m4", kind="manual", draft=None))
    assert [i.memory_id for i in queue.pending()] == ["m4", "m2", "m1", "m3"]


def test_queue_roundtrip_and_old_queue_files_without_hashes(repo):
    import json
    from mender import config, queue
    queue.add(_item(repo))
    assert queue.load()[0].draft.new_text == "Our project runs on MySQL"
    data = json.loads(config.QUEUE_FILE.read_text())
    for d in data:
        d.pop("file_hashes")                                  # queue written by an older version
    config.QUEUE_FILE.write_text(json.dumps(data))
    assert queue.load()[0].file_hashes == {} and not queue.drifted(queue.load()[0])


def test_atomic_save_leaves_no_temp_file(repo):
    from mender import config, queue
    queue.add(_item(repo))
    assert not list(config.STATE_DIR.glob("*.tmp"))
