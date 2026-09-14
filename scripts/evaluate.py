"""Run the eval set and measure baseline against RAG.

This is the script that turns "RAG seems better" into a number you can defend.

Two things are measured separately, because they fail separately:

  RETRIEVAL  -- did the right documents come back? Measured as recall against
                the `expected_docs` in questions.yaml. If this is low, no
                prompt engineering will save you.

  ANSWER     -- does the generated text contain the required facts and avoid
                the known hallucinations? Measured by substring checks.

Grading is deterministic substring matching, not an LLM judge. That is a
deliberate limitation with a deliberate reason: an LLM judge introduces a second
model whose own failures you would then have to debug, and on a corpus with
exact ground truth (a specific number, a specific env var name) substring
matching is both sufficient and unarguable. Where it is too blunt -- grading
prose quality, partial credit -- it is honestly too blunt, and notes/08 covers
what an LLM judge would add.

Usage:
    .venv\\Scripts\\python.exe -m scripts.evaluate
    .venv\\Scripts\\python.exe -m scripts.evaluate --strategy dense
    .venv\\Scripts\\python.exe -m scripts.evaluate --retrieval-only
    .venv\\Scripts\\python.exe -m scripts.evaluate --compare-strategies
    .venv\\Scripts\\python.exe -m scripts.evaluate --think
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml
from rich.console import Console
from rich.table import Table

from src import config, generation
from src.retrieval import Retriever
from src.store import VectorStore

console = Console()


# --- Grading --------------------------------------------------------------

def grade_answer(answer: str, question: dict) -> tuple[bool, list[str]]:
    """Check an answer against its must_include / must_not_include lists.

    Case-insensitive because we care whether the fact is present, not how it was
    capitalised. Returns (passed, list of failure descriptions).
    """
    lowered = answer.lower()
    failures: list[str] = []

    for required in question.get("must_include") or []:
        if required.lower() not in lowered:
            failures.append(f"missing '{required}'")

    for forbidden in question.get("must_not_include") or []:
        if forbidden.lower() in lowered:
            failures.append(f"contains '{forbidden}'")

    return (not failures), failures


def grade_retrieval(results, question: dict) -> tuple[float, set[str], set[str]]:
    """Recall of expected documents among retrieved chunks.

    Recall, not precision, because for these questions the cost of a missing
    document is a wrong answer while the cost of an extra one is some wasted
    tokens. Those are not symmetric, so a single F1 number would hide the thing
    we actually care about.

    An `absent` question expects zero documents. For those, recall is defined as
    1.0 when nothing is retrieved -- correctly finding nothing is a success, and
    dividing by an empty expected set would be undefined.
    """
    expected = set(question.get("expected_docs") or [])
    retrieved = {r.chunk.doc_id for r in results}

    if not expected:
        return (1.0 if not retrieved else 0.0), expected, retrieved

    found = expected & retrieved
    return len(found) / len(expected), expected, retrieved


# --- Runner ---------------------------------------------------------------

def run_eval(
    questions: list[dict],
    retriever: Retriever,
    *,
    strategy: str,
    top_k: int,
    retrieval_only: bool,
    think: bool,
) -> list[dict]:
    rows: list[dict] = []

    for i, q in enumerate(questions, start=1):
        console.print(
            f"[dim]({i}/{len(questions)}) {q['id']} [{q['category']}] "
            f"{q['question'][:70]}...[/dim]"
        )

        results = retriever.retrieve(q["question"], strategy=strategy, top_k=top_k)
        recall, expected, retrieved = grade_retrieval(results, q)

        row: dict = {
            "id": q["id"],
            "category": q["category"],
            "question": q["question"],
            "retrieval_recall": recall,
            "expected_docs": sorted(expected),
            "retrieved_docs": sorted(retrieved),
            "top_score": results[0].score if results else None,
        }

        if not retrieval_only:
            baseline = generation.answer_baseline(q["question"], think=think)
            grounded = generation.answer_with_context(
                q["question"], results, think=think
            )

            baseline_pass, baseline_fails = grade_answer(baseline.text, q)
            grounded_pass, grounded_fails = grade_answer(grounded.text, q)

            row.update(
                {
                    "baseline_pass": baseline_pass,
                    "baseline_failures": baseline_fails,
                    "baseline_answer": baseline.text,
                    "baseline_prompt_tokens": baseline.prompt_tokens,
                    "grounded_pass": grounded_pass,
                    "grounded_failures": grounded_fails,
                    "grounded_answer": grounded.text,
                    "grounded_prompt_tokens": grounded.prompt_tokens,
                }
            )

        rows.append(row)

    return rows


# --- Reporting ------------------------------------------------------------

def print_report(rows: list[dict], *, retrieval_only: bool) -> None:
    table = Table(title="\nPer-question results", show_header=True, header_style="bold")
    table.add_column("ID", width=4)
    table.add_column("Category", width=9)
    table.add_column("Recall", justify="right", width=7)
    if not retrieval_only:
        table.add_column("Baseline", justify="center", width=9)
        table.add_column("RAG", justify="center", width=6)
        table.add_column("Why baseline failed", overflow="fold")

    for r in rows:
        recall_str = f"{r['retrieval_recall']:.2f}"
        recall_cell = (
            f"[green]{recall_str}[/green]"
            if r["retrieval_recall"] == 1.0
            else f"[yellow]{recall_str}[/yellow]"
            if r["retrieval_recall"] > 0
            else f"[red]{recall_str}[/red]"
        )

        if retrieval_only:
            table.add_row(r["id"], r["category"], recall_cell)
        else:
            table.add_row(
                r["id"],
                r["category"],
                recall_cell,
                "[green]PASS[/green]" if r["baseline_pass"] else "[red]FAIL[/red]",
                "[green]PASS[/green]" if r["grounded_pass"] else "[red]FAIL[/red]",
                ", ".join(r["baseline_failures"])[:60] or "-",
            )

    console.print(table)

    # --- Summary ---------------------------------------------------------

    n = len(rows)
    mean_recall = sum(r["retrieval_recall"] for r in rows) / n
    perfect_recall = sum(1 for r in rows if r["retrieval_recall"] == 1.0)

    summary = Table(title="\nSummary", show_header=True, header_style="bold")
    summary.add_column("Metric")
    summary.add_column("Value", justify="right")
    summary.add_row("Questions", str(n))
    summary.add_row("Mean retrieval recall", f"{mean_recall:.1%}")
    summary.add_row("Perfect retrieval", f"{perfect_recall}/{n}")

    if not retrieval_only:
        baseline_pass = sum(1 for r in rows if r["baseline_pass"])
        grounded_pass = sum(1 for r in rows if r["grounded_pass"])
        summary.add_row("", "")
        summary.add_row("[red]Baseline correct[/red]", f"{baseline_pass}/{n}  ({baseline_pass/n:.0%})")
        summary.add_row("[green]RAG correct[/green]", f"{grounded_pass}/{n}  ({grounded_pass/n:.0%})")
        summary.add_row(
            "[bold]Improvement[/bold]",
            f"[bold]+{(grounded_pass - baseline_pass)/n:.0%}[/bold]",
        )

        mean_baseline_tokens = sum(r["baseline_prompt_tokens"] for r in rows) / n
        mean_grounded_tokens = sum(r["grounded_prompt_tokens"] for r in rows) / n
        summary.add_row("", "")
        summary.add_row("Mean prompt tokens (baseline)", f"{mean_baseline_tokens:.0f}")
        summary.add_row("Mean prompt tokens (RAG)", f"{mean_grounded_tokens:.0f}")
        summary.add_row(
            "Token cost per point gained",
            f"{(mean_grounded_tokens - mean_baseline_tokens) / max(grounded_pass - baseline_pass, 1):.0f}",
        )

    console.print(summary)

    # Per-category breakdown. The aggregate number hides the interesting part:
    # RAG's gain is not uniform, and where it does *not* help is as informative
    # as where it does.
    if not retrieval_only:
        cats = sorted({r["category"] for r in rows})
        cat_table = Table(title="\nBy category", show_header=True, header_style="bold")
        cat_table.add_column("Category")
        cat_table.add_column("n", justify="right")
        cat_table.add_column("Baseline", justify="right")
        cat_table.add_column("RAG", justify="right")
        for cat in cats:
            subset = [r for r in rows if r["category"] == cat]
            b = sum(1 for r in subset if r["baseline_pass"])
            g = sum(1 for r in subset if r["grounded_pass"])
            cat_table.add_row(cat, str(len(subset)), f"{b}/{len(subset)}", f"{g}/{len(subset)}")
        console.print(cat_table)


def compare_strategies(questions: list[dict], retriever: Retriever, top_k: int) -> None:
    """Retrieval-only sweep across all three strategies.

    Cheap to run (no generation) and the fastest way to see that dense and
    lexical retrieval fail on different questions rather than one simply
    dominating.
    """
    table = Table(title="\nRetrieval recall by strategy", show_header=True, header_style="bold")
    table.add_column("ID", width=4)
    table.add_column("Category", width=9)
    table.add_column("Dense", justify="right", width=7)
    table.add_column("Lexical", justify="right", width=8)
    table.add_column("Hybrid", justify="right", width=7)

    totals = {"dense": 0.0, "lexical": 0.0, "hybrid": 0.0}

    for q in questions:
        cells = {}
        for strat in ("dense", "lexical", "hybrid"):
            results = retriever.retrieve(q["question"], strategy=strat, top_k=top_k)
            recall, _, _ = grade_retrieval(results, q)
            totals[strat] += recall
            colour = "green" if recall == 1.0 else "yellow" if recall > 0 else "red"
            cells[strat] = f"[{colour}]{recall:.2f}[/{colour}]"
        table.add_row(q["id"], q["category"], cells["dense"], cells["lexical"], cells["hybrid"])

    n = len(questions)
    table.add_section()
    table.add_row(
        "[bold]mean[/bold]",
        "",
        f"[bold]{totals['dense']/n:.2f}[/bold]",
        f"[bold]{totals['lexical']/n:.2f}[/bold]",
        f"[bold]{totals['hybrid']/n:.2f}[/bold]",
    )
    console.print(table)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate baseline vs RAG.")
    parser.add_argument("--strategy", default="hybrid", choices=["dense", "lexical", "hybrid"])
    parser.add_argument("--top-k", type=int, default=config.TOP_K)
    parser.add_argument(
        "--retrieval-only",
        action="store_true",
        help="Skip generation. Fast -- use while tuning chunking or retrieval.",
    )
    parser.add_argument(
        "--compare-strategies",
        action="store_true",
        help="Retrieval-only sweep across dense, lexical, and hybrid.",
    )
    parser.add_argument(
        "--think",
        action="store_true",
        help="Enable the model's reasoning mode. ~15x slower; see generation.py.",
    )
    args = parser.parse_args()

    questions = yaml.safe_load(
        (config.EVAL_DIR / "questions.yaml").read_text(encoding="utf-8")
    )["questions"]

    store = VectorStore.load()
    retriever = Retriever(store)

    console.print(
        f"[bold]Eval[/bold]  {len(questions)} questions · {len(store)} chunks · "
        f"strategy={args.strategy} · top_k={args.top_k}"
    )

    if args.compare_strategies:
        compare_strategies(questions, retriever, args.top_k)
        return

    if not args.retrieval_only:
        generation.check_model_available()
        est = len(questions) * 2 * (75 if args.think else 6)
        console.print(f"[dim]Estimated runtime: ~{est // 60} min[/dim]\n")

    started = time.time()
    rows = run_eval(
        questions,
        retriever,
        strategy=args.strategy,
        top_k=args.top_k,
        retrieval_only=args.retrieval_only,
        think=args.think,
    )
    elapsed = time.time() - started

    print_report(rows, retrieval_only=args.retrieval_only)
    console.print(f"\n[dim]Completed in {elapsed:.0f}s[/dim]")

    # Persist the run. Comparing runs is the whole point -- a single score tells
    # you nothing, the delta after a config change tells you everything.
    runs_dir = config.EVAL_DIR / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = runs_dir / f"{stamp}-{args.strategy}-k{args.top_k}.json"
    out.write_text(
        json.dumps(
            {
                "timestamp": stamp,
                "config": {
                    "strategy": args.strategy,
                    "top_k": args.top_k,
                    "think": args.think,
                    "embedding_model": config.EMBEDDING_MODEL,
                    "generation_model": config.OLLAMA_MODEL,
                    "chunk_target_tokens": config.CHUNK_TARGET_TOKENS,
                    "min_similarity": config.MIN_SIMILARITY,
                },
                "results": rows,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    console.print(f"[dim]Saved -> {out.relative_to(config.PROJECT_ROOT)}[/dim]")


if __name__ == "__main__":
    main()
