"""Loading source documents off disk.

Kept separate from chunking so that adding a new source type (PDFs, a Confluence
export, your Obsidian vault) means writing one loader, not touching the rest of
the pipeline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import config


@dataclass
class Document:
    doc_id: str
    title: str
    source_path: str
    body: str
    metadata: dict


_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_frontmatter(raw: str) -> tuple[dict, str]:
    """Split YAML frontmatter from the markdown body.

    Frontmatter is metadata the author already wrote down -- doc IDs, owners,
    review dates. Parsing it rather than ignoring it gives us fields to filter
    and cite on for free.

    A note on what we do *not* do: we do not embed the frontmatter. It is
    mostly dates and names, which add tokens without adding retrievable
    meaning, and a stray date can pull a chunk into results for any query that
    mentions a year. The title is the exception -- it goes into the context
    header instead.
    """
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        return {}, raw

    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        # Malformed frontmatter should not take down an indexing run over one
        # bad file. Treat it as body text and carry on.
        return {}, raw

    if not isinstance(meta, dict):
        return {}, raw

    return meta, raw[match.end():]


def load_documents(corpus_dir: Path | None = None) -> list[Document]:
    """Load every markdown file under `corpus_dir`."""
    corpus_dir = corpus_dir or config.CORPUS_DIR
    if not corpus_dir.exists():
        raise FileNotFoundError(
            f"Corpus directory not found: {corpus_dir}. "
            "Create it and add markdown files, or point config.CORPUS_DIR elsewhere."
        )

    documents: list[Document] = []

    for path in sorted(corpus_dir.rglob("*.md")):
        raw = path.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(raw)

        # Title resolution order: explicit frontmatter, then the first H1, then
        # the filename. The filename fallback is why corpus files should be
        # named meaningfully -- `notes.md` produces a useless context header.
        title = meta.get("title")
        if not title:
            h1 = re.search(r"^#\s+(.*)$", body, re.MULTILINE)
            title = h1.group(1).strip() if h1 else path.stem.replace("-", " ").title()

        doc_id = meta.get("doc_id") or path.stem

        documents.append(
            Document(
                doc_id=str(doc_id),
                title=str(title),
                source_path=str(path.relative_to(config.PROJECT_ROOT)),
                body=body,
                metadata=meta,
            )
        )

    if not documents:
        raise ValueError(f"No markdown files found under {corpus_dir}")

    return documents
