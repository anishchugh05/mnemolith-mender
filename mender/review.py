import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from . import queue
from .mnemolith_client import apply_confirm, apply_replace

console = Console()

def review() -> None:
    items = queue.pending()
    if not items:
        console.print("[green]Nothing to review.[/green]")
        return
    console.print(f"[bold]REVIEW QUEUE: {len(items)} pending[/bold] (lowest confidence first)\n")
    for n, it in enumerate(items, 1):
        console.print(Panel(f'[bold]{it.memory_id}[/bold]: "{it.old_text}"\n'
                            f"Why flagged: {it.triage_why}",
                            title=f"{n}/{len(items)}  {it.kind.upper()}"))
        if it.diff:
            console.print(Syntax(it.diff, "diff", theme="ansi_dark"))
        if it.kind == "replace" and it.draft:
            console.print(Panel(
                f"{it.draft.new_text}\n\n[dim]{it.draft.reason}[/dim]\n"
                f"Model confidence: {it.draft.confidence:.2f} (self-reported)",
                title="Draft", border_style="cyan"))
            choices, text = "[a]pprove [e]dit [r]eject [s]kip", None
        elif it.kind == "confirm":
            console.print("[dim]Change looks harmless: memory is probably still true.[/dim]")
            choices = "[a]pprove (mark still true) [r]eject [s]kip"
        else:
            console.print("[yellow]Needs a manual decision.[/yellow]")
            choices = "[r]eject (dismiss) [s]kip"

        while True:
            c = typer.prompt(choices, default="s").strip().lower()[:1]
            if c == "s":
                break
            if c == "r":
                queue.set_status(it.memory_id, "rejected")
                console.print("Rejected, nothing changed.\n")
                break
            if c in ("a", "e") and it.kind == "replace" and it.draft:
                text = it.draft.new_text
                if c == "e":
                    text = typer.prompt("New memory text", default=text)
                console.print(apply_replace(it.memory_id, text, it.files))
                queue.set_status(it.memory_id, "approved")
                console.print()
                break
            if c == "a" and it.kind == "confirm":
                console.print(apply_confirm(it.memory_id))
                queue.set_status(it.memory_id, "approved")
                console.print()
                break
            console.print("Not an option here.")