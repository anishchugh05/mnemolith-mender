from conftest import reply


def test_triage_parses_json_wrapped_in_prose(repo):
    from mender.triage import _parse
    r = _parse('Sure!\n```json\n{"invalidated": false, "why": "comment only"}\n```')
    assert r.invalidated is False and r.why == "comment only"


def test_triage_unparseable_output_escalates(repo):
    from mender.triage import _parse
    assert _parse("I think maybe").invalidated is True
    assert _parse("").invalidated is True
    assert _parse('{"why": "missing key"}').invalidated is True


def test_draft_confidence_is_clamped(repo):
    from mender.drafter import _to_draft
    assert _to_draft({"new_text": " x ", "confidence": 7}).confidence == 1.0
    assert _to_draft({"new_text": "x", "confidence": "nope"}).confidence == 0.0


def test_cli_lists_commands_once(repo):
    from typer.testing import CliRunner
    from mender.cli import app
    out = CliRunner().invoke(app, ["--help"]).output
    for cmd in ("init", "run", "review", "ui", "watch", "hook", "models", "doctor", "stats"):
        assert cmd in out
    assert "stats-cmd" not in out


def test_init_excludes_state_dir_from_target_repo(repo):
    from typer.testing import CliRunner
    from mender.cli import app
    CliRunner().invoke(app, ["init"])
    assert ".mender/" in (repo.path / ".git" / "info" / "exclude").read_text()


def test_run_without_key_exits_cleanly(repo, monkeypatch):
    from typer.testing import CliRunner
    from mender import config
    from mender.cli import app
    monkeypatch.setattr(config, "API_KEY", "")
    res = CliRunner().invoke(app, ["run"])
    assert res.exit_code == 1 and "NEBIUS_API_KEY" in res.output
