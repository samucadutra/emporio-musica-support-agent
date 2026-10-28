"""Command-line interface: the `emporio` console script."""

import json

import typer
from rich.console import Console

from emporio_musica_support_agent.config import Settings
from emporio_musica_support_agent.data.loader import DataFileNotFoundError, policy_path
from emporio_musica_support_agent.llm import FastEmbedEmbeddings
from emporio_musica_support_agent.rag.index import PolicyIndex

app = typer.Typer(
    name="emporio",
    help="Empório da Música customer-support agent (Lia).",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def main() -> None:
    """Empório da Música customer-support agent."""


def make_policy_index(settings: Settings) -> PolicyIndex:
    """The policy index for these settings; the embedding model loads only when used."""
    embeddings = FastEmbedEmbeddings(settings.embedding_model, settings.models_cache_dir)
    return PolicyIndex(
        settings.chroma_dir,
        embeddings,
        policy_path(settings.data_dir),
        settings.embedding_model,
    )


@app.command()
def ingest(
    force: bool = typer.Option(False, "--force", help="Rebuild even if the index is up to date."),
) -> None:
    """Build or refresh the policy index; a no-op when nothing changed."""
    console = Console()
    settings = Settings()
    try:
        report = make_policy_index(settings).build(force=force)
    except DataFileNotFoundError as error:
        console.print(f"[red]Error:[/red] {error}", soft_wrap=True)  # keep the path copyable
        raise typer.Exit(code=1) from error
    if report.built:
        console.print(f"Indexed {report.chunk_count} policy chunks into {settings.chroma_dir}")
        console.print_json(json.dumps(report.manifest, ensure_ascii=False))
    else:
        console.print(f"Policy index is up to date ({report.chunk_count} chunks).")
