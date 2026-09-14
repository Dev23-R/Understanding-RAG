"""Central configuration.

Every tunable in the pipeline lives here rather than being scattered through the
modules that use it. That is a deliberate choice for this project specifically:
the whole point is to change one knob at a time and observe what happens to
retrieval quality. Knobs buried in function defaults are knobs nobody turns.
"""

from __future__ import annotations

from pathlib import Path

# --- Paths ----------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = PROJECT_ROOT / "corpus"
INDEX_DIR = PROJECT_ROOT / "index"
EVAL_DIR = PROJECT_ROOT / "evals"

# --- Chunking -------------------------------------------------------------

# Target chunk size in *tokens* of the embedding model, not characters.
#
# Why tokens: the embedding model has a hard input limit (512 tokens for
# bge-small). Anything past that is silently truncated -- you get an embedding
# back, no error, but the tail of your chunk contributed nothing. Sizing in
# characters means you discover this by noticing bad retrieval, which is a
# miserable way to find out.
#
# Why 320 and not the full 512: we leave headroom because we prepend the
# document title and heading path to each chunk (see chunking.py). That context
# prefix costs tokens, and it is worth more than the extra body text.
CHUNK_TARGET_TOKENS = 320

# Overlap between adjacent chunks, in tokens.
#
# Overlap exists to stop a fact being severed at a chunk boundary. Without it, a
# sentence spanning the split is in neither chunk in a retrievable form. The cost
# is index size and some duplicate results.
CHUNK_OVERLAP_TOKENS = 64

# A chunk smaller than this is merged into its neighbour rather than stored
# alone. Tiny chunks ("## Rollback" and nothing else) score erratically: they
# have so few tokens that a single term match dominates the similarity.
CHUNK_MIN_TOKENS = 48

# --- Embedding ------------------------------------------------------------

# BAAI/bge-small-en-v1.5: 384 dimensions, 133MB, 512-token limit.
#
# Chosen over the more common all-MiniLM-L6-v2 because BGE models are trained
# with an asymmetric query/passage objective, which is what retrieval actually
# is -- a short question matched against a long passage. MiniLM is trained for
# symmetric similarity (sentence A vs sentence B) and is measurably weaker at
# question->document matching.
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384

# BGE models require this instruction prefix on *queries only*, never on the
# documents being indexed. Getting this wrong is the single most common silent
# bug when using BGE: retrieval still works, just noticeably worse, with no
# error to tell you. See embedding.py for the full explanation.
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# --- Retrieval ------------------------------------------------------------

# How many chunks to retrieve and put in the prompt.
#
# More is not better. Every retrieved chunk is context the model must read, and
# irrelevant chunks actively degrade answers -- the model treats retrieved text
# as authoritative and will reason from a plausible-looking wrong chunk. This is
# the "context stuffing" failure mode; notes/06 covers it.
TOP_K = 5

# Reciprocal Rank Fusion constant for hybrid retrieval. 60 is the value from the
# original RRF paper (Cormack et al. 2009) and is not especially sensitive.
RRF_K = 60

# Chunks scoring below this cosine similarity are dropped even if they are in
# the top-k. This is what lets the system answer "I don't know" instead of
# confidently citing the least-irrelevant chunk it could find.
#
# 0.30 is tuned for bge-small on this corpus. It is not a universal constant --
# different embedding models have completely different similarity distributions.
MIN_SIMILARITY = 0.30

# --- Generation -----------------------------------------------------------

OLLAMA_MODEL = "qwen3:8b"

# Context window to request from Ollama.
#
# This matters more than it looks. Ollama's default num_ctx is 4096 regardless
# of what the model supports. With 5 retrieved chunks plus a system prompt you
# can exceed that, and Ollama silently truncates from the *start* of the prompt
# -- which is where the system instructions live. Symptom: the model ignores
# your grounding instructions for no apparent reason.
OLLAMA_NUM_CTX = 16384

# Deterministic generation. We are comparing baseline against RAG on the same
# questions; sampling noise would show up as a quality difference that is really
# just randomness.
OLLAMA_TEMPERATURE = 0.0

OLLAMA_SEED = 42
