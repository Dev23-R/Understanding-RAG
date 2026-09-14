"""Does a similarity threshold separate answerable from unanswerable questions?

Short answer on this corpus: no. This script reproduces that result.

It exists because "set a minimum similarity score to avoid hallucinating on
out-of-scope questions" is advice you will read everywhere, it sounds obviously
right, and it does not survive contact with measurement. Run it, look at the
overlap, and you will never again trust a threshold to be your hallucination
defence.

Usage:
    .venv\\Scripts\\python.exe -m scripts.threshold_analysis
"""

from __future__ import annotations

import yaml
from rich.console import Console
from rich.table import Table

from src import config, embedding
from src.store import VectorStore

console = Console()


def main() -> None:
    store = VectorStore.load()
    questions = yaml.safe_load(
        (config.EVAL_DIR / "questions.yaml").read_text(encoding="utf-8")
    )["questions"]

    table = Table(
        title="Top-1 cosine similarity by question",
        show_header=True,
        header_style="bold",
    )
    table.add_column("ID", width=4)
    table.add_column("Category", width=9)
    table.add_column("Top-1", justify="right", width=7)
    table.add_column("Question", overflow="fold")

    answerable: list[tuple[str, float]] = []
    absent: list[tuple[str, float]] = []

    rows = []
    for q in questions:
        qv = embedding.embed_query(q["question"])
        hits = store.search(qv, 1)
        top = hits[0][1] if hits else 0.0
        rows.append((q, top))
        (absent if q["category"] == "absent" else answerable).append((q["id"], top))

    # Sort by score so the overlap is visible at a glance rather than needing
    # to be worked out from an id-ordered list.
    for q, top in sorted(rows, key=lambda r: -r[1]):
        colour = "yellow" if q["category"] == "absent" else "cyan"
        table.add_row(
            q["id"],
            f"[{colour}]{q['category']}[/{colour}]",
            f"{top:.3f}",
            q["question"][:62],
        )

    console.print(table)

    if not absent:
        console.print("[yellow]No `absent` questions in the set.[/yellow]")
        return

    ans_min = min(s for _, s in answerable)
    ans_min_id = min(answerable, key=lambda kv: kv[1])[0]
    abs_max = max(s for _, s in absent)
    abs_max_id = max(absent, key=lambda kv: kv[1])[0]

    console.print(
        f"\nLowest-scoring ANSWERABLE question:   {ans_min_id} at {ans_min:.3f}"
    )
    console.print(
        f"Highest-scoring UNANSWERABLE question: {abs_max_id} at {abs_max:.3f}"
    )

    if abs_max < ans_min:
        console.print(
            f"\n[green]Separable.[/green] Any threshold in "
            f"({abs_max:.3f}, {ans_min:.3f}) splits them cleanly."
        )
    else:
        console.print(
            f"\n[red]Not separable.[/red] The highest unanswerable question "
            f"({abs_max:.3f}) outscores the lowest answerable one ({ans_min:.3f})."
        )
        console.print(
            "\nAny threshold high enough to reject "
            f"[yellow]{abs_max_id}[/yellow] also rejects "
            f"[cyan]{ans_min_id}[/cyan], which the corpus answers directly."
        )
        console.print(
            "\n[bold]What this means:[/bold] cosine similarity measures topical "
            "relatedness, not whether an answer is present. Deciding 'the topic "
            "is right but the specific fact is missing' requires reading the "
            "question and the passage together -- which the embedding never "
            "did, because the passage was embedded before any question existed.\n"
            "\nThe component that CAN make that judgement is the generating "
            "model, via an explicit instruction to decline. The threshold is a "
            "filter for genuine garbage, not a hallucination defence."
        )

    # Show what it would actually cost to threshold aggressively.
    console.print("\n")
    cost = Table(title="Cost of raising the threshold", show_header=True, header_style="bold")
    cost.add_column("Threshold", justify="right")
    cost.add_column("Answerable rejected", justify="right")
    cost.add_column("Unanswerable rejected", justify="right")
    for t in (0.30, 0.50, 0.60, 0.65, 0.70, 0.75):
        ans_rejected = sum(1 for _, s in answerable if s < t)
        abs_rejected = sum(1 for _, s in absent if s < t)
        colour = "red" if ans_rejected else "green"
        cost.add_row(
            f"{t:.2f}",
            f"[{colour}]{ans_rejected}/{len(answerable)}[/{colour}]",
            f"{abs_rejected}/{len(absent)}",
        )
    console.print(cost)


if __name__ == "__main__":
    main()
