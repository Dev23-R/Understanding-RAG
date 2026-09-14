"""Ask a question, with and without retrieval, side by side.

This is the script that makes the point. Same model, same question, same
decoding settings -- the only variable is whether retrieved context is in the
prompt.

Usage:
    .venv\\Scripts\\python.exe -m scripts.ask "what do I do when Atlas queue depth grows?"
    .venv\\Scripts\\python.exe -m scripts.ask "..." --strategy dense
    .venv\\Scripts\\python.exe -m scripts.ask "..." --show-chunks
    .venv\\Scripts\\python.exe -m scripts.ask "..." --rag-only
"""

from __future__ import annotations

import argparse

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src import config, generation
from src.retrieval import Retriever
from src.store import VectorStore

console = Console()


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask with and without RAG.")
    parser.add_argument("question", help="The question to ask.")
    parser.add_argument(
        "--strategy",
        default="hybrid",
        choices=["dense", "lexical", "hybrid"],
        help="Retrieval strategy (default: hybrid).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=config.TOP_K,
        help=f"Chunks to retrieve (default: {config.TOP_K}).",
    )
    parser.add_argument(
        "--show-chunks",
        action="store_true",
        help="Print the retrieved chunk text, not just the citations.",
    )
    parser.add_argument(
        "--rag-only",
        action="store_true",
        help="Skip the baseline answer (faster when you only want the result).",
    )
    parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="Print the full assembled prompt sent to the model.",
    )
    args = parser.parse_args()

    generation.check_model_available()

    store = VectorStore.load()
    retriever = Retriever(store)

    console.rule(f"[bold]{args.question}")

    # --- Retrieval ---------------------------------------------------------

    results = retriever.retrieve(
        args.question, strategy=args.strategy, top_k=args.top_k
    )

    if results:
        table = Table(
            title=f"Retrieved ({args.strategy}, top {args.top_k})",
            show_header=True,
            header_style="bold",
        )
        table.add_column("#", width=3, justify="right")
        table.add_column("Source")
        table.add_column("Cosine", justify="right", width=8)
        table.add_column("Found by")
        for i, r in enumerate(results, start=1):
            table.add_row(
                str(i),
                r.chunk.citation,
                f"{r.score:.3f}",
                "+".join(r.sources),
            )
        console.print(table)
    else:
        console.print(
            "[yellow]Nothing retrieved above the similarity threshold "
            f"({config.MIN_SIMILARITY}).[/yellow] The grounded answer should "
            "decline to answer."
        )

    if args.show_chunks:
        for i, r in enumerate(results, start=1):
            console.print(
                Panel(
                    r.chunk.body.strip()[:1200],
                    title=f"[{i}] {r.chunk.citation}  (cos {r.score:.3f})",
                    border_style="dim",
                )
            )

    # --- Generation --------------------------------------------------------

    if not args.rag_only:
        console.print("\n[dim]Generating baseline (no retrieval)...[/dim]")
        baseline = generation.answer_baseline(args.question)
        console.print(
            Panel(
                baseline.text,
                title="[red]WITHOUT retrieval[/red]",
                border_style="red",
                subtitle=(
                    f"{baseline.prompt_tokens} prompt / "
                    f"{baseline.completion_tokens} completion tokens · "
                    f"{baseline.duration_s:.1f}s"
                ),
            )
        )

    console.print("\n[dim]Generating grounded answer...[/dim]")
    grounded = generation.answer_with_context(args.question, results)
    console.print(
        Panel(
            grounded.text,
            title="[green]WITH retrieval[/green]",
            border_style="green",
            subtitle=(
                f"{grounded.prompt_tokens} prompt / "
                f"{grounded.completion_tokens} completion tokens · "
                f"{grounded.duration_s:.1f}s"
            ),
        )
    )

    if args.show_prompt:
        console.print(
            Panel(
                grounded.prompt,
                title="Full prompt sent to the model",
                border_style="dim",
            )
        )

    # The token delta is worth seeing every time. Retrieval is not free -- it
    # buys accuracy with prompt tokens and latency. Knowing the exchange rate
    # is what lets you decide whether it is worth it for a given workload.
    if not args.rag_only:
        delta = grounded.prompt_tokens - baseline.prompt_tokens
        console.print(
            f"\n[dim]Retrieval cost: +{delta} prompt tokens "
            f"({grounded.prompt_tokens} vs {baseline.prompt_tokens}).[/dim]"
        )


if __name__ == "__main__":
    main()
