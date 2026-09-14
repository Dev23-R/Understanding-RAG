---
tags: [reference]
---

# Project Map

Everything lives under `D:\RAG Project`.

```
corpus/                  8 fictional documents -- the knowledge base
src/                     the pipeline
  config.py              every tunable, in one place
  corpus.py              loading documents, parsing frontmatter
  chunking.py            structure-aware splitting + context headers
  embedding.py           text -> vectors, query/passage asymmetry
  store.py               the vector index (numpy)
  retrieval.py           dense, lexical, hybrid (RRF)
  generation.py          prompts + Ollama calls
scripts/                 command-line entry points
  index.py               build the index
  ask.py                 side-by-side baseline vs RAG
  evaluate.py            run the eval set
  threshold_analysis.py  reproduce the threshold finding
evals/
  questions.yaml         14 questions with dual ground truth
  runs/                  timestamped results (gitignored)
index/                   built artifacts (gitignored)
Understanding RAG/       this vault
.venv/                   Python 3.12 environment (gitignored)
```

## Reading order for the code

Follow the data, not the filenames:

1. **`config.py`** — every decision the pipeline makes is a constant here, each
   with a comment explaining why that value.
2. **`corpus.py`** → **`chunking.py`** — documents become chunks. Most of the
   leverage in the whole system is in `chunk_document`.
3. **`embedding.py`** — chunks become vectors. Note the two separate functions
   for passages and queries; that separation is the point.
4. **`store.py`** — vectors become an index. The entire search is
   `self.embeddings @ query_vector`.
5. **`retrieval.py`** — queries become ranked chunks. Three strategies.
6. **`generation.py`** — chunks become an answer. The prompt is doing more work
   than it looks.

## Where each concept note maps to code

| Note | Code |
|---|---|
| [[02 - Why Chunking Decides Everything]] | `src/chunking.py` |
| [[03 - Embeddings and the Query-Passage Asymmetry]] | `src/embedding.py` |
| [[04 - The Vector Store Is One Matrix Multiply]] | `src/store.py` |
| [[05 - Dense vs Lexical vs Hybrid]] | `src/retrieval.py` |
| [[06 - Context Is Not Free]] | `src/generation.py`, `config.TOP_K` |
| [[07 - The Grounding Prompt Does More Than You Think]] | `GROUNDED_SYSTEM` in `src/generation.py` |
| [[08 - Measuring Whether Any Of This Worked]] | `scripts/evaluate.py`, `evals/questions.yaml` |

## Stack

| Component | Choice | Why |
|---|---|---|
| Embeddings | `BAAI/bge-small-en-v1.5` | Asymmetric retrieval training, 133MB, CPU-fast |
| Vector store | numpy | Transparent — see [[04 - The Vector Store Is One Matrix Multiply]] |
| Lexical | `rank_bm25` | Simple, no index to maintain at this scale |
| Generation | `qwen3:8b` via Ollama | Local, free, no API key |
| Python | 3.12 | Best ML wheel coverage |
| torch | CPU build | ~200MB vs ~2.5GB for CUDA; embedding 53 chunks takes 2.7s |

Everything runs locally. No API keys, no network calls after the initial model
downloads.

## Swapping components

The interfaces are narrow on purpose:

- **Different embedding model** — change `EMBEDDING_MODEL` and `EMBEDDING_DIM` in
  `config.py`, rebuild. Check the model card for its query prefix convention and
  update `BGE_QUERY_PREFIX`. `MIN_SIMILARITY` will need retuning — score
  distributions differ per model.
- **Different generation model** — change `OLLAMA_MODEL`. Note `/no_think` is
  Qwen3-specific and becomes a silent no-op elsewhere.
- **A real vector database** — replace `VectorStore` with anything offering
  `search(query_vector, top_k) -> [(idx, score)]`. Nothing else changes.
- **Your own documents** — drop markdown into `corpus/` and rebuild. Frontmatter
  `title` and `doc_id` are used if present.
