from conftest import switch_to_mysql


def _mem(repo, files=("docker-compose.yml",), text="Our project runs on Postgres"):
    from mender.models import FileLink, StaleMemory
    from mender import gitutil
    return StaleMemory(id="m1", text=text, reason="changed",
                       files=[FileLink(f, gitutil.blob_hash(f)) for f in files])


def test_diff_shows_changed_lines(repo):
    from mender import payload
    mem = _mem(repo)
    switch_to_mysql(repo)
    p = payload.build(mem)
    d = payload.diff_text(p.changes[0])
    assert "-    image: postgres:16" in d and "+    image: mysql:8" in d


def test_uncommitted_edit_gets_old_version_from_saved_hash(repo):
    from mender import payload
    mem = _mem(repo)
    switch_to_mysql(repo)                      # not committed
    c = payload.build(mem).changes[0]
    assert "postgres" in c.old and "mysql" in c.new and c.changed


def test_multi_file_only_one_changed(repo):
    from mender import payload
    mem = _mem(repo, files=("docker-compose.yml", "README.md"))
    switch_to_mysql(repo)
    p = payload.build(mem)
    by = {c.path: c for c in p.changes}
    assert by["docker-compose.yml"].changed and not by["README.md"].changed
    assert "unchanged since the memory was saved" in payload.diff_text(by["README.md"])
    assert payload.current_paths(p) == ["docker-compose.yml", "README.md"]


def test_old_version_unavailable(repo):
    from mender import payload
    from mender.models import FileLink, StaleMemory
    mem = StaleMemory("m1", "x", "changed", [FileLink("docker-compose.yml", None)])
    d = payload.diff_text(payload.build(mem).changes[0])
    assert "old version unavailable" in d and "postgres" in d


def test_deleted_file(repo):
    from mender import payload
    mem = _mem(repo)
    (repo.path / "docker-compose.yml").unlink()
    p = payload.build(mem)
    assert p.changes[0].deleted and payload.all_gone(p)
    assert payload.current_paths(p) == []


def test_rename_untracked_exact_move_is_found_by_content_hash(repo):
    from mender import payload
    mem = _mem(repo)
    (repo.path / "docker-compose.yml").rename(repo.path / "compose.yaml")   # not git-added
    p = payload.build(mem)
    c = p.changes[0]
    assert c.renamed_to == "compose.yaml" and not c.deleted and not payload.all_gone(p)
    assert payload.current_paths(p) == ["compose.yaml"]
    assert "RENAMED" in payload.diff_text(c)


def test_rename_with_edits_found_by_git(repo):
    from mender import payload
    mem = _mem(repo)
    repo.git("mv", "docker-compose.yml", "compose.yaml")
    (repo.path / "compose.yaml").write_text("services:\n  db:\n    image: postgres:16\n    ports: ['5432:5432']\n")
    c = payload.build(mem).changes[0]
    assert c.renamed_to == "compose.yaml"
    assert "+    ports" in payload.diff_text(c)


def test_dependency_bumps(repo):
    from mender import payload
    from mender.models import FileChange
    req = FileChange("requirements.txt", "next==14.2.0\nrequests>=2.0\n", "next==15.0.0\nrequests>=2.0\n")
    assert payload.dep_bumps(req) == ["next 14.2.0 -> 15.0.0"]
    pkg = FileChange("web/package.json", '{"dependencies": {"next": "^14.2.0"}}',
                     '{"dependencies": {"next": "^15.0.1"}}')
    assert payload.dep_bumps(pkg) == ["next 14.2.0 -> 15.0.1"]
    assert payload.dep_bumps(FileChange("app.py", "a", "b")) == []
