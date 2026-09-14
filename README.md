# Understanding RAG

A working retrieval-augmented generation system, built from scratch to measure
what retrieval actually does to a model's output — and documented throughout with
the reasoning behind each decision.

Everything runs locally. No API keys, no network calls after the initial model
downloads.

## The result

Same model, same questions, same decoding settings. The only variable is whether
retrieved context is in the prompt.

| | Baseline | With RAG |
|---|---:|---:|
| Correct answers | **2/14 (14%)** | **14/14 (100%)** |
| Mean prompt tokens | 54 | 1,234 |

The two baseline passes were lucky guesses — questions where generic industry
advice happens to match Meridian's actual policy. On knowing anything specific
about the corpus, the baseline scores 0/14.

### The clearest single example

> **Q: What should I do when the AtlasQueueDepthGrowing alert fires, and what is
> the maximum replica count?**

**Without retrieval**, the model pattern-matched "Atlas" to MongoDB Atlas and
produced a confident, detailed, entirely fabricated incident procedure — shard
balancers, chunk migration, replica set members. It stated the max replica count
is 16, *which is correct*, for completely the wrong reason (16 is the MongoDB
replica set member limit).

**With retrieval**, it gave the real answer: scale with
`kubectl -n meridian scale deploy/atlas --replicas=12`, max 16 because Atlas holds
one PostGIS connection per replica against a 200-connection cap.

A right answer for a wrong reason is still a failure, because the reason is what
you reason from next. Full write-up in the vault.

## Documentation

Detailed notes live in the Obsidian vault at `Understanding RAG/` — open that
folder as a vault, or read the markdown directly. Start with `Start Here.md`.

Nine concept notes cover each pipeline stage and why it's built that way, plus
three findings including two negative results that contradicted expectations
going in.

## Quick start

```powershell
# Build the index
.\.venv\Scripts\python.exe -m scripts.index --stats

# Ask something, with and without retrieval
.\.venv\Scripts\python.exe -m scripts.ask "Is Atlas a database?"

# Run the eval
.\.venv\Scripts\python.exe -m scripts.evaluate

# Reproduce the threshold finding
.\.venv\Scripts\python.exe -m scripts.threshold_analysis
```

Full command reference in `Understanding RAG/Reference/Commands.md`.

## Layout

```
corpus/       8 fictional documents -- the knowledge base
src/          the pipeline: chunking, embedding, store, retrieval, generation
scripts/      CLI entry points
evals/        14 questions with dual ground truth (retrieval + generation)
Understanding RAG/   the Obsidian vault
```

## Stack

| Component | Choice |
|---|---|
| Embeddings | `BAAI/bge-small-en-v1.5` (384d, local, CPU) |
| Vector store | ~120 lines of numpy — deliberately, see the vault |
| Lexical search | BM25 via `rank_bm25` |
| Generation | `qwen3:8b` via Ollama |
| Python | 3.12, CPU-only torch |

## Two things this project measured that are worth knowing

**Similarity thresholds do not separate answerable from unanswerable questions.**
On this corpus the unanswerable *"What is Meridian's parental leave policy?"*
scores 0.688 — higher than the answerable *"What language is Sentry written
in?"* at 0.615. No threshold splits them; rejecting the former costs you a third
of the questions the corpus answers. The reason is structural: a passage is
embedded before any question exists, so its vector encodes topic, not
answer-presence. The refusal has to come from the prompt, and it does.

**A cheap grader produces false failures.** The eval initially marked a correct
answer as wrong because substring matching can't distinguish "Atlas *is* MongoDB
Atlas" from "Atlas is *not* MongoDB Atlas". A false failure you don't investigate
sends you optimising against a bug in your ruler.

## Setup notes

Requires Git, Python 3.12, and Ollama with `qwen3:8b` pulled. The `.venv` and
`index/` directories are gitignored — recreate with:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
ollama pull qwen3:8b
.\.venv\Scripts\python.exe -m scripts.index
```
