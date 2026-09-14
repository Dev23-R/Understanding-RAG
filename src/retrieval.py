"""Finding the right chunks.

Three strategies are implemented so they can be compared directly, because the
most common misconception about RAG is that dense embedding search is simply
the better technology and keyword search is what we did before we had it. That
is not what the evidence shows. They fail in different, complementary places:

  Dense retrieval understands meaning but blurs specifics. It knows "the thing
  that generates manifests" relates to Quill. It is *worse* than keyword search
  at finding the exact string `QUILL_PG_POOL_SIZE`, because rare tokens get
  averaged away in a 384-dimensional summary of a whole passage.

  Keyword retrieval (BM25) matches exact terms and weights rare ones heavily. It
  nails identifiers, error codes, and proper nouns. It scores zero on a query
  that shares no vocabulary with the passage, no matter how obviously related
  the two are to a human.

Hybrid retrieval runs both and fuses the rankings. In this corpus you can watch
the split happen: "what is the ULID prefix for settlements?" is a BM25 question,
"what happens if compliance screening is unavailable?" is a dense question, and
a system that only does one will lose one of them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from . import config, embedding
from .chunking import Chunk
from .store import VectorStore


@dataclass
class RetrievalResult:
    chunk: Chunk
    score: float
    rank: int
    # Which strategies surfaced this chunk, for inspection. Seeing that a chunk
    # was found by BM25 alone and missed entirely by dense search is where the
    # intuition for hybrid retrieval actually comes from.
    sources: list[str]


_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def _tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokenisation for BM25.

    Underscores are kept as word characters on purpose: `QUILL_PG_POOL_SIZE`
    and `sibling_shipment_id` are single meaningful terms in this corpus, and
    splitting them into fragments would scatter their matches across common
    words like "size" and "id".
    """
    return _TOKEN_RE.findall(text.lower())


class Retriever:
    """Dense, lexical, and hybrid retrieval over one index."""

    def __init__(self, store: VectorStore) -> None:
        self.store = store
        # BM25 is built in memory at load time. It is cheap (a term-frequency
        # table) and there is no benefit to persisting it for a corpus this
        # size.
        self._bm25 = BM25Okapi([_tokenize(c.text) for c in store.chunks])

    # --- Individual strategies -------------------------------------------

    def dense(self, query: str, top_k: int) -> list[tuple[int, float]]:
        """Semantic search via embedding similarity."""
        query_vector = embedding.embed_query(query)
        return self.store.search(query_vector, top_k)

    def lexical(self, query: str, top_k: int) -> list[tuple[int, float]]:
        """BM25 keyword search.

        BM25 scores a document by how many query terms it contains, weighted by
        how rare each term is across the corpus (a match on "Vantage" is worth
        far more than a match on "the"), and dampened by document length so long
        documents do not win by sheer surface area.

        Scores are unbounded and corpus-relative -- a BM25 score of 8.0 means
        nothing on its own. This is precisely why fusing dense and BM25 by
        adding their scores does not work, and why we fuse by *rank* below.
        """
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(enumerate(scores), key=lambda kv: -kv[1])[:top_k]
        return [(int(i), float(s)) for i, s in ranked if s > 0]

    # --- Fusion -----------------------------------------------------------

    def hybrid(self, query: str, top_k: int) -> list[tuple[int, float, list[str]]]:
        """Combine dense and lexical rankings with Reciprocal Rank Fusion.

        RRF scores each document as sum over strategies of 1 / (k + rank),
        where rank is 1-based and k is a smoothing constant (60, from the
        original paper).

        Why rank-based fusion rather than score-based: cosine similarity lives
        in [-1, 1] and BM25 is unbounded and corpus-dependent. There is no
        principled way to add them -- any normalisation you invent (min-max,
        z-score) is sensitive to the particular result set and will swing wildly
        between queries. Ranks are directly comparable by construction: "third
        best according to this strategy" means the same thing regardless of
        strategy.

        The k constant controls how sharply top ranks are favoured. With k=60,
        rank 1 scores 1/61 and rank 2 scores 1/62 -- close together, so a
        document ranked highly by *both* strategies beats one ranked first by
        only one. That is the behaviour we want: agreement between independent
        methods is strong evidence.

        We over-fetch (3x top_k) from each strategy before fusing, because a
        chunk that lands at rank 8 in both is a better answer than one at rank 1
        in a single strategy, and it cannot win if it was never retrieved.
        """
        fetch = top_k * 3

        dense_hits = self.dense(query, fetch)
        lexical_hits = self.lexical(query, fetch)

        fused: dict[int, float] = {}
        sources: dict[int, list[str]] = {}

        for rank, (idx, _score) in enumerate(dense_hits, start=1):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (config.RRF_K + rank)
            sources.setdefault(idx, []).append("dense")

        for rank, (idx, _score) in enumerate(lexical_hits, start=1):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (config.RRF_K + rank)
            sources.setdefault(idx, []).append("lexical")

        ordered = sorted(fused.items(), key=lambda kv: -kv[1])[:top_k]
        return [(idx, score, sources[idx]) for idx, score in ordered]

    # --- Public entry point ----------------------------------------------

    def retrieve(
        self,
        query: str,
        *,
        strategy: str = "hybrid",
        top_k: int | None = None,
        min_similarity: float | None = None,
    ) -> list[RetrievalResult]:
        """Retrieve chunks for a query.

        `min_similarity` applies only to dense and hybrid strategies, and it is
        always measured against the *cosine* score, never the fused RRF score --
        an RRF score has no absolute meaning, so thresholding it would be
        arbitrary.

        A WARNING ABOUT THIS THRESHOLD, measured on this corpus rather than
        assumed.

        It is tempting to believe the threshold is what makes "I don't know"
        possible -- that unanswerable questions score low and get filtered. On
        this corpus that is false, and the numbers are worth internalising:

            q12 "What is Meridian's parental leave policy?"   -> 0.688
                (nothing in the corpus touches HR policy)
            q10 "What language is Sentry written in?"         -> 0.615
                (answered directly in ARCH-001 and REF-006)

        The unanswerable question scores HIGHER than the answerable one. No
        threshold value separates them; any cutoff that rejects q12 also
        rejects several questions the corpus answers perfectly well.

        The reason is structural, not a tuning failure. Cosine similarity
        measures topical relatedness. "Meridian's parental leave policy" really
        is close to "Meridian Data Retention and Residency Policy" -- shared
        subject, shared vocabulary, same document genre. A 384-dimensional
        summary of a passage has no way to encode "this text is about the right
        topic but does not contain the specific fact asked for". That is a
        judgement about a question-document *pair*, and the passage was embedded
        without ever seeing the question.

        So what actually produces honest refusals? The prompt. Rule 1 of
        GROUNDED_SYSTEM tells the model to say the documentation does not cover
        something, and the model -- which unlike the embedding can read the
        question and the context together -- is the component capable of making
        that call. The threshold is a cheap filter for genuine garbage, not a
        hallucination defence. Treating it as one is a common and expensive
        mistake.

        Run `python -m scripts.threshold_analysis` to reproduce these numbers
        and see the full distribution.
        """
        top_k = top_k or config.TOP_K
        threshold = (
            config.MIN_SIMILARITY if min_similarity is None else min_similarity
        )

        results: list[RetrievalResult] = []

        if strategy == "dense":
            for rank, (idx, score) in enumerate(self.dense(query, top_k), start=1):
                if score < threshold:
                    continue
                results.append(
                    RetrievalResult(self.store.chunks[idx], score, rank, ["dense"])
                )

        elif strategy == "lexical":
            for rank, (idx, score) in enumerate(self.lexical(query, top_k), start=1):
                results.append(
                    RetrievalResult(self.store.chunks[idx], score, rank, ["lexical"])
                )

        elif strategy == "hybrid":
            # Recompute true cosine similarity for threshold purposes. The RRF
            # score tells us the ordering; the cosine tells us whether the best
            # result is actually any good.
            query_vector = embedding.embed_query(query)
            for rank, (idx, rrf_score, srcs) in enumerate(
                self.hybrid(query, top_k), start=1
            ):
                cosine = float(self.store.embeddings[idx] @ query_vector)
                # A chunk found by BM25 with a strong exact-term match is kept
                # even if its cosine is low. That is the entire point of hybrid
                # retrieval -- vocabulary the embedding blurred away.
                if cosine < threshold and "lexical" not in srcs:
                    continue
                results.append(
                    RetrievalResult(self.store.chunks[idx], cosine, rank, srcs)
                )

        else:
            raise ValueError(
                f"Unknown strategy '{strategy}'. Use 'dense', 'lexical', or 'hybrid'."
            )

        return results
