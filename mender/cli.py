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
    return (f"{c['stale']} stale ({c['skipped']} already queued) | "
            f"{c['harmless']} harmless (Nano only) | "
            f"{c['drafted']} drafted (Ultra) | {c['manual']} need manual review")

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
    console.print(_summary(go(force)))
    console.print("Run [bold]mender review[/bold] to approve or reject.")

@app.command()
def review():
    """Approve, edit or reject drafts. Nothing is saved until you approve."""
    from .review import review as go
    go()

@app.command()
def watch(interval: int = typer.Option(5, help="Seconds between checks.")):
    """Poll for stale memories (catches uncommitted edits too) and draft fixes."""
    _need_key()
    from .pipeline import run as go
    console.print(f"Watching {config.REPO} every {interval}s. Ctrl-C to stop.")
    try:
        while True:
            c = go()
            if c["drafted"] or c["harmless"] or c["manual"]:
                console.print(f"[{time.strftime('%H:%M:%S')}] {_summary(c)}")
                console.print("  Run [bold]mender review[/bold] when ready.")
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

@app.command()
def stats_cmd():
    """Model calls, tokens and latency so far."""
    for model, s in stats.summarize().items():
        console.print(f"{model}: {s['calls']} calls, {s['prompt']} in / "
                      f"{s['completion']} out tokens, {s['latency']:.1f}s")
    console.print(f"Pending drafts: {len(queue.pending())}")

app.command("stats")(stats_cmd)

if __name__ == "__main__":
    app()