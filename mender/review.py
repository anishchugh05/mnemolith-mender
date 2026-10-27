import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from . import actions, queue

console = Console()

def _batch_confirms(items) -> None:
    """Harmless-change confirmations are low stakes; offer to approve them in one go."""
    ok = [i for i in items if i.kind == "confirm" and not queue.drifted(i)]
    if len(ok) < 2:
        return
    if typer.confirm(f"{len(ok)} memories look unaffected by the change "
                     f"({', '.join(i.memory_id for i in ok)}). Mark them all still true?",
                     default=False):
        for i in ok:
            try:
                console.print(f"{i.memory_id}: {actions.approve(i.memory_id)}")
            except Exception as e:
                console.print(f"[red]{i.memory_id}: {e}[/red]")
        console.print()

def review() -> None:
    items = queue.pending()
    if not items:
        console.print("[green]Nothing to review.[/green]")
        return
    console.print(f"[bold]REVIEW QUEUE: {len(items)} pending[/bold] (lowest confidence first)\n")
    _batch_confirms(items)
    items = queue.pending()
    for n, it in enumerate(items, 1):
        console.print(Panel(f'[bold]{it.memory_id}[/bold]: "{it.old_text}"\n'
                            f"Why flagged: {it.triage_why}",
                            title=f"{n}/{len(items)}  {it.kind.upper()}"))
        if it.kind != "manual" and queue.drifted(it):
            console.print(f"[yellow]{it.memory_id}: files changed since this was drafted. "
                          "Skipping. Run `mender run` to re-draft.[/yellow]\n")
            continue
        if it.diff:
            console.print(Syntax(it.diff, "diff", theme="ansi_dark"))
        if it.kind == "replace" and it.draft:
            console.print(Panel(
                f"{it.draft.new_text}\n\n[dim]{it.draft.reason}[/dim]\n"
                f"Model confidence: {it.draft.confidence:.2f} (self-reported)",
                title="Draft", border_style="cyan"))
            choices = "[a]pprove [e]dit [r]eject [s]kip"
        elif it.kind == "confirm":
            console.print("[dim]Memory looks unaffected by the change: probably still true.[/dim]")
            choices = "[a]pprove (mark still true) [r]eject [s]kip"
        else:
            console.print("[yellow]Every linked file was deleted. Retire the memory if it no longer "
                          "applies, or dismiss to leave it as is.[/yellow]")
            choices = "[t] retire [r]eject (dismiss) [s]kip"

        while True:
            c = typer.prompt(choices, default="s").strip().lower()[:1]
            if c == "s":
                break
            try:
                if c == "t" and it.kind == "manual":
                    console.print(actions.retire(it.memory_id), "\n")
                    break
                if c == "r":
                    actions.reject(it.memory_id)
                    console.print("Rejected, nothing changed.\n")
                    break
                if c in ("a", "e") and it.kind == "replace" and it.draft:
                    text = it.draft.new_text
                    if c == "e":
                        text = typer.prompt("New memory text", default=text)
                    console.print(actions.approve(it.memory_id, text), "\n")
                    break
                if c == "a" and it.kind == "confirm":
                    console.print(actions.approve(it.memory_id), "\n")
                    break
            except actions.Drifted as e:
                console.print(f"[yellow]{e}[/yellow]\n")
                break
            except Exception as e:
                console.print(f"[red]{e}[/red]")
                break
            console.print("Not an option here.")
