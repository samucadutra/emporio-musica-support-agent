"""Command-line interface: the `emporio` console script."""

import typer

app = typer.Typer(
    name="emporio",
    help="Empório da Música customer-support agent (Lia).",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def main() -> None:
    """Empório da Música customer-support agent."""
