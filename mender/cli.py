import typer
from rich.console import Console
from . import config, queue, stats

app = typer.Typer(help="Mender: draft fixes for stale Mnemolith memories.")
console = Console()

@app.command()
def init():
    """Keep Mender's local state out of the target repo's git history."""
    ex = config.REPO / ".git" / "info" / "exclude"
    ex.parent.mkdir(parents=True, exist_ok=True)
    cur = ex.read_text() if ex.exists() else ""
    if ".mender/" not in cur:
        ex.write_text(cur + ("\n" if cur and not cur.endswith("\n") else "") + ".mender/\n")
    config.STATE_DIR.mkdir(exist_ok=True)
    console.print(f"Ready. Watching repo: {config.REPO}")

@app.command()
def run():
    """Find stale memories and draft fixes (nothing is written to Mnemolith)."""
    if not config.API_KEY:
        raise typer.Exit("NEBIUS_API_KEY is not set (check your .env).")
    from .pipeline import run as go
    c = go()
    console.print(f"{c['stale']} stale | {c['harmless']} harmless (Nano only) | "
                  f"{c['drafted']} drafted (Ultra) | {c['manual']} need manual review")
    console.print("Run [bold]mender review[/bold] to approve or reject.")

@app.command()
def review():
    """Approve, edit or reject drafts. Nothing is saved until you approve."""
    from .review import review as go
    go()

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