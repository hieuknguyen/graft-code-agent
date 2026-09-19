from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.text import Text

console = Console()

def print_banner():
    banner = """
  ██████╗ ██████╗  █████╗ ███████╗████████╗     █████╗  ██████╗ ███████╗███╗   ██╗████████╗
 ██╔════╝ ██╔══██╗██╔══██╗██╔════╝╚══██╔══╝    ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝
 ██║  ███╗██████╔╝███████║█████╗     ██║       ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   
 ██║   ██║██╔══██╗██╔══██║██╔══╝     ██║       ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   
 ╚██████╔╝██║  ██║██║  ██║██║        ██║       ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   
  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝        ╚═╝       ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   
    """
    console.print(Panel(
        Text(banner, style="bold cyan"),
        subtitle="[bold green]AI Surgical Coding Agent with AST Grafting & Dependency Graph[/bold green]",
        border_style="cyan"
    ))

def print_token_stats(tokens: dict):
    if not tokens:
        return
    p = tokens.get("prompt_tokens", 0)
    c = tokens.get("completion_tokens", 0)
    tot = tokens.get("total_tokens", 0) or (p + c)
    console.print(f"[bold cyan]Input:[/] {p:,} tok | [bold green]Output:[/] {c:,} tok | [bold magenta]Tổng:[/] {tot:,} tok")

def render_diff(diff_text: str):
    lines = diff_text.splitlines()
    render_text = Text()
    for line in lines:
        if line.startswith("+") and not line.startswith("+++"):
            render_text.append(line + "\n", style="bold green")
        elif line.startswith("-") and not line.startswith("---"):
            render_text.append(line + "\n", style="bold red")
        elif line.startswith("@"):
            render_text.append(line + "\n", style="bold cyan")
        else:
            render_text.append(line + "\n", style="dim white")
    console.print(Panel(render_text, title="[bold yellow]Unified Diff (Phẫu thuật cấy ghép)[/bold yellow]", border_style="yellow"))
