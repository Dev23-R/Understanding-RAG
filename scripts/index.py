"""Build the vector index from the corpus.

Usage:
    .venv\\Scripts\\python.exe -m scripts.index
    .venv\\Scripts\\python.exe -m scripts.index --stats
"""

from __future__ import annotations

import argparse
import time
from collections import Counter

from rich.console import Console
from rich.table import Table

from src import config, corpus, embedding
from src.chunking import chunk_document
from src.store import VectorStore

console = Console()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the RAG index.")
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print per-document chunk statistics after building.",
    )
    args = parser.parse_args()

    started = time.time()

    console.print(f"[bold]Loading corpus[/bold] from {config.CORPUS_DIR}")
    documents = corpus.load_documents()
    console.print(f"  {len(documents)} documents")

    console.print(f"\n[bold]Loading embedding model[/bold] {config.EMBEDDING_MODEL}")
    console.print("  (first run downloads ~130MB)")
    embedding.get_model()

    console.print("\n[bold]Chunking[/bold]")
    all_chunks = []
    for doc in documents:
        chunks = chunk_document(
            doc_id=doc.doc_id,
            doc_title=doc.title,
            source_path=doc.source_path,
            body=doc.body,
            metadata=doc.metadata,
            count_tokens=embedding.count_tokens,
        )
        all_chunks.extend(chunks)
        console.print(f"  {doc.doc_id:<16} {len(chunks):>3} chunks  {doc.title}")

    console.print(f"\n[bold]Embedding[/bold] {len(all_chunks)} chunks")
    vectors = embedding.embed_passages(
        [c.text for c in all_chunks], show_progress=True
    )

    store = VectorStore(all_chunks, vectors)
    out = store.save()

    elapsed = time.time() - started
    console.print(
        f"\n[green]Index built[/green] -> {out}  "
        f"({len(all_chunks)} chunks, {vectors.shape[1]}d, {elapsed:.1f}s)"
    )

    if args.stats:
        _print_stats(all_chunks)


def _print_stats(chunks) -> None:
    token_counts = [c.token_count for c in chunks]
    by_doc = Counter(c.doc_id for c in chunks)

    table = Table(title="\nChunk size distribution", show_header=True)
    table.add_column("Metric")
    table.add_column("Tokens", justify="right")
    ordered = sorted(token_counts)
    table.add_row("min", str(ordered[0]))
    table.add_row("p50", str(ordered[len(ordered) // 2]))
    table.add_row("p90", str(ordered[int(len(ordered) * 0.9)]))
    table.add_row("max", str(ordered[-1]))
    table.add_row("mean", f"{sum(ordered) / len(ordered):.0f}")
    console.print(table)

    # A chunk at or near the model's 512-token limit is a warning sign: the
    # tail may have been truncated during embedding, silently.
    oversized = [c for c in chunks if c.token_count > 500]
    if oversized:
        console.print(
            f"\n[yellow]Warning:[/yellow] {len(oversized)} chunk(s) near the "
            f"512-token embedding limit. Their tails may be silently truncated."
        )
        for c in oversized[:5]:
            console.print(f"  {c.citation} ({c.token_count} tokens)")

    doc_table = Table(title="\nChunks per document", show_header=True)
    doc_table.add_column("Document")
    doc_table.add_column("Chunks", justify="right")
    for doc_id, count in by_doc.most_common():
        doc_table.add_row(doc_id, str(count))
    console.print(doc_table)


if __name__ == "__main__":
    main()
