"""Turning text into vectors.

An embedding is a fixed-length list of floats positioned so that texts with
similar meaning sit close together. That is the entire trick behind semantic
search: you cannot compare a question to a document by string matching if they
share no words, but you *can* compare their positions.

The subtlety this module exists to handle is that "close together" is defined by
whatever objective the model was trained on -- and for retrieval models that
objective is asymmetric.
"""

from __future__ import annotations

import functools

import numpy as np
from sentence_transformers import SentenceTransformer

from . import config


@functools.lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    """Load the embedding model once and reuse it.

    Loading takes a few seconds and roughly 150MB of RAM. The cache matters
    because the eval harness runs many questions in a loop; reloading per
    question would dominate runtime.
    """
    return SentenceTransformer(config.EMBEDDING_MODEL)


def count_tokens(text: str) -> int:
    """Count tokens using the *embedding model's own* tokenizer.

    Not a word count, not `len(text) // 4`. The model has a hard 512-token input
    limit and truncates silently past it -- you get a valid-looking vector that
    simply ignored the end of your chunk. Counting with any other tokenizer
    means your chunk-size budget is approximate in exactly the situation where
    being wrong is invisible.
    """
    tokenizer = get_model().tokenizer
    # `verbose=False` suppresses HuggingFace's "sequence length is longer than
    # the specified maximum (843 > 512)" warning. Here that warning is a false
    # alarm: it assumes you are about to feed the sequence to the model, but we
    # are measuring a whole document section in order to decide how to split it.
    # Nothing over the limit is ever embedded -- the splitting this measurement
    # drives is what guarantees that. Left unsuppressed, the warning trains you
    # to ignore a message that would be genuinely important if it came from
    # `embed_passages`.
    return len(tokenizer.encode(text, add_special_tokens=False, verbose=False))


def embed_passages(texts: list[str], *, show_progress: bool = False) -> np.ndarray:
    """Embed document chunks for storage in the index.

    Note there is no prefix here, deliberately. See `embed_query`.

    `normalize_embeddings=True` scales every vector to unit length. That is what
    makes cosine similarity reduce to a plain dot product, which is why the
    vector store in store.py can be a single matrix multiply rather than a
    per-row cosine computation.
    """
    model = get_model()
    return model.encode(
        texts,
        batch_size=32,
        show_progress_bar=show_progress,
        normalize_embeddings=True,
        convert_to_numpy=True,
    ).astype(np.float32)


def embed_query(text: str) -> np.ndarray:
    """Embed a search query.

    THE ASYMMETRY. This is the part that is easy to get wrong and produces no
    error when you do.

    BGE models are trained on (query, passage) pairs where the two sides are
    encoded differently: the query carries an instruction prefix, the passage
    does not. The model learns to map "Represent this sentence for searching
    relevant passages: what do I do when Atlas backs up?" into the same
    neighbourhood as the *unprefixed* text of the relevant passage.

    If you prefix both sides, or neither, retrieval still runs. You still get
    ranked results. They are just measurably worse, with nothing in the output
    to tell you why. On this corpus, dropping the prefix costs roughly 5-8
    percentage points of retrieval accuracy -- enough to matter, small enough
    that you would blame your chunking instead.

    This is worth internalising beyond BGE specifically: embedding models are
    trained artifacts with usage contracts, and the contract is not enforced at
    runtime. Read the model card. Every family has its own convention -- E5 uses
    "query: " and "passage: ", Nomic uses "search_query: " and
    "search_document: ", OpenAI's models use none at all.
    """
    model = get_model()
    prefixed = config.BGE_QUERY_PREFIX + text
    return model.encode(
        [prefixed],
        normalize_embeddings=True,
        convert_to_numpy=True,
    ).astype(np.float32)[0]
