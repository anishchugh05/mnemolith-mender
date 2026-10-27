import os
import sys

# --repo has to be applied before config is imported (REPO resolves at import time).
for _i, _a in enumerate(sys.argv):
    if _a == "--repo" and _i + 1 < len(sys.argv):
        os.environ["MENDER_REPO"] = sys.argv[_i + 1]
    elif _a.startswith("--repo="):
        os.environ["MENDER_REPO"] = _a.split("=", 1)[1]

import time
import typer
from rich.console import Console
from . import config, queue, stats

app = typer.Typer(help="Mender: draft fixes for stale Mnemolith memories.",
                  no_args_is_help=True)
console = Console()

@app.callback()
def main(repo: str = typer.Option(
        None, "--repo", help="Repo to check. Goes before the command: mender --repo PATH run")):
    pass

def _need_key():
    if not config.API_KEY:
        console.print("[red]NEBIUS_API_KEY is not set (check your .env).[/red]")
        raise typer.Exit(1)

def _summary(c: dict) -> str:
    s = (f"{c['stale']} stale ({c['skipped']} unchanged since last run) | "
         f"{c['harmless']} harmless (Nano only) | {c['drafted']} drafted (Ultra) | "
         f"{c['still_true']} still true (Ultra) | {c['manual']} need manual review")
    if c["errors"]:
        s += f" | [red]{c['errors']} failed (will retry): {c['last_error']}[/red]"
    return s

def _active(c: dict) -> bool:
    return bool(c["harmless"] or c["drafted"] or c["still_true"] or c["manual"] or c["errors"])

@app.command()
def init():
    """Keep Mender's local state out of the target repo's git history."""
    ex = config.REPO / ".git" / "info" / "exclude"
    ex.parent.mkdir(parents=True, exist_ok=True)
    cur = ex.read_text() if ex.exists() else ""
    if ".mender/" not in cur:
        ex.write_text(cur + ("\n" if cur and not cur.endswith("\n") else "") + ".mender/\n")
    config.STATE_DIR.mkdir(exist_ok=True)
    console.print(f"Ready. Repo: {config.REPO}")

@app.command()
def run(force: bool = typer.Option(False, "--force",
        help="Re-draft memories that are already queued or were rejected.")):
    """Find stale memories and draft fixes (nothing is written to Mnemolith)."""
    _need_key()
    from .pipeline import run as go
    c = go(force)
    if c["busy"]:
        console.print("Another Mender run is already in progress; skipping.")
        return
    console.print(_summary(c))
    console.print("Run [bold]mender review[/bold] (or [bold]mender ui[/bold]) to approve or reject.")

@app.command()
def review():
    """Approve, edit or reject drafts in the terminal. Nothing is saved until you approve."""
    from .review import review as go
    go()

@app.command()
def ui(port: int = typer.Option(7391, help="Local port."),
       no_browser: bool = typer.Option(False, "--no-browser", help="Don't open a browser tab.")):
    """Review drafts in a local web page (same queue, same safety checks)."""
    from .ui import serve
    serve(port, open_browser=not no_browser)

@app.command()
def watch(interval: int = typer.Option(5, help="Seconds between checks.")):
    """Poll for stale memories (catches uncommitted edits too) and draft fixes."""
    _need_key()
    from .pipeline import run as go
    console.print(f"Watching {config.REPO} every {interval}s. Ctrl-C to stop.")
    try:
        while True:
            try:
                c = go()
                if _active(c):
                    console.print(f"[{time.strftime('%H:%M:%S')}] {_summary(c)}")
                    console.print("  Run [bold]mender review[/bold] or [bold]mender ui[/bold] when ready.")
            except Exception as e:  # engine restarting, network blip: keep watching
                console.print(f"[yellow]{time.strftime('%H:%M:%S')} check failed: {e}[/yellow]")
            time.sleep(interval)
    except KeyboardInterrupt:
        console.print("Stopped.")

@app.command()
def hook():
    """Install a git post-commit hook so Mender runs after every commit."""
    hooks = config.REPO / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    config.STATE_DIR.mkdir(exist_ok=True)
    path = hooks / "post-commit"
    marker = "# mender-hook"
    cur = path.read_text() if path.exists() else "#!/bin/sh\n"
    if marker in cur:
        console.print("Hook already installed.")
        return
    line = (f'{marker}\nMENDER_REPO="{config.REPO}" "{sys.executable}" -m mender.cli run '
            f'>> "{config.STATE_DIR}/hook.log" 2>&1 &\n')
    path.write_text(cur + ("" if cur.endswith("\n") else "\n") + line)
    path.chmod(0o755)
    console.print(f"Installed. After each commit, Mender runs in the background "
                  f"(log: {config.STATE_DIR}/hook.log).")

def _nemotron_ids(all_models: bool = False) -> list[str]:
    from .llm import _get_client
    ids = sorted(m.id for m in _get_client().models.list())
    return ids if all_models else [i for i in ids if "nemotron" in i.lower()]

@app.command()
def models(all: bool = typer.Option(False, "--all", help="List every model, not just Nemotron.")):
    """List the model IDs your Token Factory key can use."""
    _need_key()
    for i in _nemotron_ids(all):
        mark = " [green]<- Nano (current)[/green]" if i == config.MODEL_NANO else \
               " [green]<- Ultra (current)[/green]" if i == config.MODEL_ULTRA else ""
        console.print(i + mark)

@app.command()
def doctor(live: bool = typer.Option(False, "--live",
           help="Also test tool calling on the Ultra model (spends a few tokens).")):
    """Check the setup: repo, Mnemolith, key, model IDs, and (with --live) tool calling."""
    ok = lambda m: console.print(f"[green]ok[/green]   {m}")
    bad = lambda m: console.print(f"[red]FAIL[/red] {m}")
    if sys.version_info >= (3, 10): ok(f"Python {sys.version.split()[0]}")
    else: bad("Python 3.10+ is required")
    import subprocess
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=config.REPO,
                       capture_output=True, text=True)
    (ok if r.returncode == 0 else bad)(f"repo: {config.REPO}" + ("" if r.returncode == 0 else " (not a git repo)"))
    try:
        from . import mnemolith_client
        ok(f"Mnemolith importable, project '{mnemolith_client.project()}'")
    except Exception as e:
        bad(f"Mnemolith: {e}")
    if not config.API_KEY:
        bad("NEBIUS_API_KEY is not set"); raise typer.Exit(1)
    ok("NEBIUS_API_KEY is set")
    try:
        ids = _nemotron_ids()
    except Exception as e:
        bad(f"couldn't list models ({e}). Check the key and credits."); raise typer.Exit(1)
    ok(f"Token Factory reachable, {len(ids)} Nemotron models")
    for label, mid in (("Nano", config.MODEL_NANO), ("Ultra", config.MODEL_ULTRA)):
        if mid in ids: ok(f"{label} model: {mid}")
        else:
            bad(f"{label} model '{mid}' is not served. Pick from `mender models` and set "
                f"MENDER_{label.upper()}=... in .env")
    if config.TAVILY_KEY: ok("TAVILY_API_KEY is set")
    else: console.print("[yellow]warn[/yellow] TAVILY_API_KEY not set (dependency-bump research disabled)")
    if live:
        from . import llm, tools
        try:
            resp = llm.chat("doctor", config.MODEL_ULTRA,
                            [{"role": "user", "content": "Use the grep_repo tool to check if 'postgres' appears in the repo."}],
                            tools=[t for t in tools.TOOLS if t["function"]["name"] == "grep_repo"],
                            max_tokens=500)
            if resp.choices[0].message.tool_calls: ok("Ultra tool calling works (agent path will be used)")
            else: console.print("[yellow]warn[/yellow] Ultra did not call the tool; the one-prompt fallback will be used")
        except Exception as e:
            bad(f"Ultra call failed: {e}")

def stats_cmd():
    """Model calls, tokens, and how many memories each model tier handled."""
    for model, s in stats.summarize().items():
        console.print(f"{model}: {s['calls']} calls, {s['prompt']} in / "
                      f"{s['completion']} out tokens, {s['latency']:.1f}s")
    r = stats.routing()
    seen = r["harmless"] + r["drafted"] + r["still_true"] + r["manual"]
    if seen:
        console.print(f"Routing: {seen} decisions | {r['harmless']} handled by Nano alone | "
                      f"{r['drafted'] + r['still_true']} sent to Ultra | {r['manual']} manual")
    console.print(f"Pending drafts: {len(queue.pending())}")

app.command("stats")(stats_cmd)

if __name__ == "__main__":
    app()
