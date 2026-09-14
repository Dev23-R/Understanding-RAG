"""Splitting documents into retrievable units.

Chunking is the highest-leverage and least-discussed part of a RAG system. The
embedding model and the vector store get all the attention, but if your chunks
are wrong, nothing downstream can recover: retrieval can only ever return a
chunk you created, so a fact split across two chunks is a fact the system cannot
cleanly answer about.

Three design decisions are made here, each documented at its implementation:

1. Split on document *structure* (markdown headings), not fixed character counts.
2. Prepend a context header (title + heading path) to every chunk.
3. Measure size in embedding-model tokens, not characters.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from . import config


@dataclass
class Chunk:
    """One retrievable unit.

    `text` is what gets embedded and shown to the model. `body` is the original
    text without the context header -- kept so we can show a clean excerpt to a
    human without the synthetic prefix cluttering it.
    """

    doc_id: str
    doc_title: str
    source_path: str
    heading_path: list[str]
    body: str
    text: str
    token_count: int
    chunk_index: int
    metadata: dict = field(default_factory=dict)

    @property
    def citation(self) -> str:
        """Human-readable source reference, e.g. 'OPS-002 > Common alerts'."""
        if self.heading_path:
            return f"{self.doc_id} > {' > '.join(self.heading_path)}"
        return self.doc_id


# --- Section splitting ----------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass
class _Section:
    heading_path: list[str]
    lines: list[str]

    def text(self) -> str:
        return "\n".join(self.lines).strip()


def _split_into_sections(markdown: str) -> list[_Section]:
    """Break a markdown document into sections along heading boundaries.

    Why structural rather than fixed-size: a heading is the author telling you
    where one topic ends and the next begins. That is free, high-quality
    segmentation signal, and throwing it away in favour of "every 1000
    characters" means routinely cutting through the middle of a table or
    separating a mitigation step from the alert it belongs to.

    In this corpus that difference is concrete. The on-call runbook documents
    four alerts. Structural chunking keeps each alert with its own mitigation.
    Fixed-size chunking at 1000 characters splits `SentryVantageTimeout` so that
    "do not disable the circuit breaker" lands in a different chunk from the
    alert name -- and a query about that alert then retrieves a chunk that
    omits the single most important instruction in the document.

    We track the full heading *path* (["Common alerts", "AtlasQueueDepthGrowing"])
    rather than just the nearest heading, because the nearest heading alone is
    often meaningless out of context. "Mitigation" tells you nothing; "Common
    alerts > AtlasQueueDepthGrowing > Mitigation" tells you everything.
    """
    sections: list[_Section] = []
    current_path: list[str] = []
    current_lines: list[str] = []
    in_code_fence = False

    def flush() -> None:
        if current_lines and "".join(current_lines).strip():
            sections.append(_Section(list(current_path), list(current_lines)))

    for line in markdown.splitlines():
        # Headings inside fenced code blocks are not headings. Without this
        # guard, a shell comment like `# scale the deployment` in a runbook
        # snippet starts a spurious new section.
        if line.strip().startswith("```"):
            in_code_fence = not in_code_fence
            current_lines.append(line)
            continue

        match = _HEADING_RE.match(line) if not in_code_fence else None
        if match:
            flush()
            current_lines = []
            level = len(match.group(1))
            title = match.group(2).strip()
            # Truncate the path to this heading's depth, then append. A level-2
            # heading replaces any previous level-2 and discards deeper levels.
            current_path = current_path[: level - 1]
            while len(current_path) < level - 1:
                current_path.append("")
            current_path.append(title)
        else:
            current_lines.append(line)

    flush()
    return sections


# --- Size-bounded packing -------------------------------------------------

def _split_oversized(
    text: str,
    count_tokens: Callable[[str], int],
    target: int,
    overlap: int,
) -> list[str]:
    """Split a section that exceeds the target size.

    Structural chunking alone is not enough -- a section can be longer than the
    embedding model's input limit, and a long section produces a vague embedding
    regardless (averaging many topics into one vector makes it close to nothing
    in particular).

    We split on paragraph boundaries first and fall back to sentences, so we
    only ever cut mid-paragraph when a single paragraph is itself too long. The
    overlap is applied in *paragraph* units rather than raw tokens, which keeps
    the seams readable.
    """
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = count_tokens(para)

        # A single paragraph over budget: split it on sentence boundaries.
        if para_tokens > target:
            if current:
                chunks.append("\n\n".join(current))
                current, current_tokens = [], 0
            sentences = re.split(r"(?<=[.!?])\s+", para)
            buf: list[str] = []
            buf_tokens = 0
            for sent in sentences:
                sent_tokens = count_tokens(sent)
                if buf and buf_tokens + sent_tokens > target:
                    chunks.append(" ".join(buf))
                    buf, buf_tokens = [], 0
                buf.append(sent)
                buf_tokens += sent_tokens
            if buf:
                chunks.append(" ".join(buf))
            continue

        if current and current_tokens + para_tokens > target:
            chunks.append("\n\n".join(current))
            # Carry trailing paragraphs forward as overlap.
            carried: list[str] = []
            carried_tokens = 0
            for prev in reversed(current):
                prev_tokens = count_tokens(prev)
                if carried_tokens + prev_tokens > overlap:
                    break
                carried.insert(0, prev)
                carried_tokens += prev_tokens
            current = carried
            current_tokens = carried_tokens

        current.append(para)
        current_tokens += para_tokens

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def chunk_document(
    *,
    doc_id: str,
    doc_title: str,
    source_path: str,
    body: str,
    metadata: dict,
    count_tokens: Callable[[str], int],
) -> list[Chunk]:
    """Turn one document into a list of chunks ready for embedding."""
    sections = _split_into_sections(body)

    # Merge sections that are too small to stand alone. A heading with one line
    # under it embeds badly -- too few tokens means a single shared term can
    # dominate the similarity score and surface it for unrelated queries.
    merged: list[_Section] = []
    for section in sections:
        if (
            merged
            and count_tokens(section.text()) < config.CHUNK_MIN_TOKENS
            and count_tokens(merged[-1].text()) < config.CHUNK_TARGET_TOKENS
        ):
            merged[-1].lines.extend([""] + section.lines)
        else:
            merged.append(section)

    chunks: list[Chunk] = []
    index = 0

    for section in merged:
        section_text = section.text()
        if not section_text:
            continue

        pieces = (
            [section_text]
            if count_tokens(section_text) <= config.CHUNK_TARGET_TOKENS
            else _split_oversized(
                section_text,
                count_tokens,
                config.CHUNK_TARGET_TOKENS,
                config.CHUNK_OVERLAP_TOKENS,
            )
        )

        heading_path = [h for h in section.heading_path if h]

        for piece in pieces:
            # --- The context header -------------------------------------
            #
            # Every chunk is prefixed with its document title and heading path
            # before embedding. This is contextual retrieval, and it is one of
            # the cheapest large wins available.
            #
            # The problem it solves: chunk text is written assuming the reader
            # has the surrounding document. A chunk reading "Raise the pool size
            # via QUILL_PG_POOL_SIZE -- it is safe up to 30" never says the word
            # "alert", never says "Quill is the document service", and may not
            # even say "Postgres". A user asking "what do I do when Quill runs
            # out of database connections?" may not match it.
            #
            # Prefixing "Meridian On-Call Runbook > Common alerts >
            # QuillPoolExhausted" puts those missing terms into the embedded
            # text, so the chunk is findable by the vocabulary people actually
            # search with.
            #
            # We store the prefixed form in `text` (embedded, shown to the
            # model) and the clean form in `body` (shown to humans).
            header_parts = [doc_title]
            header_parts.extend(heading_path)
            header = " > ".join(header_parts)
            text = f"{header}\n\n{piece}"

            chunks.append(
                Chunk(
                    doc_id=doc_id,
                    doc_title=doc_title,
                    source_path=source_path,
                    heading_path=heading_path,
                    body=piece,
                    text=text,
                    token_count=count_tokens(text),
                    chunk_index=index,
                    metadata=dict(metadata),
                )
            )
            index += 1

    return chunks
