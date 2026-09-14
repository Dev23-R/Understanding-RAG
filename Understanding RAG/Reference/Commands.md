---
tags: [reference]
---

# Commands

All commands run from `D:\RAG Project`. The venv Python is used directly, so
there's no need to activate anything.

## Build the index

```powershell
.\.venv\Scripts\python.exe -m scripts.index
```

With chunk statistics — useful after changing any chunking parameter:

```powershell
.\.venv\Scripts\python.exe -m scripts.index --stats
```

Rebuild after: editing anything in `corpus/`, or changing `CHUNK_*`,
`EMBEDDING_MODEL` in `config.py`.

## Ask a question

Side by side, with and without retrieval:

```powershell
.\.venv\Scripts\python.exe -m scripts.ask "What should I do when the AtlasQueueDepthGrowing alert fires?"
```

Useful flags:

| Flag | Effect |
|---|---|
| `--strategy dense\|lexical\|hybrid` | Pick the retrieval strategy (default hybrid) |
| `--top-k N` | Number of chunks retrieved (default 5) |
| `--show-chunks` | Print the retrieved text, not just citations |
| `--show-prompt` | Print the full assembled prompt |
| `--rag-only` | Skip the baseline — much faster |

Seeing the actual prompt is the fastest way to understand what the model is
working from:

```powershell
.\.venv\Scripts\python.exe -m scripts.ask "Is Atlas a database?" --show-prompt --rag-only
```

## Run the eval

Full run, baseline vs RAG, ~2.5 minutes:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate
```

Retrieval only — no generation, a few seconds. **Use this while tuning chunking
or retrieval**, since generation is 95% of the runtime and irrelevant to those
changes:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate --retrieval-only
```

Compare all three strategies:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate --compare-strategies
```

With the model's reasoning mode — roughly 15x slower, ~35 min:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate --think
```

Results are written to `evals/runs/<timestamp>-<strategy>-k<n>.json` with the
full config that produced them.

## Reproduce the threshold finding

```powershell
.\.venv\Scripts\python.exe -m scripts.threshold_analysis
```

See [[Similarity Thresholds Do Not Separate]].

## Ollama

```powershell
ollama list                  # installed models
ollama pull qwen3:8b         # (re)download the model
ollama ps                    # what is loaded in VRAM right now
```

Ollama runs as a background service on Windows and starts with the machine. If a
script reports it can't connect, check `ollama list` in a fresh terminal.

## Experiments worth running

Each of these changes exactly one thing, which is the only way to learn anything
from the result.

```powershell
# Does the context header earn its tokens?
#   Comment out the header line in chunking.py, rebuild, compare recall.
.\.venv\Scripts\python.exe -m scripts.index
.\.venv\Scripts\python.exe -m scripts.evaluate --retrieval-only

# How much does the BGE query prefix matter?
#   Set BGE_QUERY_PREFIX = "" in config.py -- no rebuild needed, queries only.
.\.venv\Scripts\python.exe -m scripts.evaluate --retrieval-only

# Does more context help or hurt?
.\.venv\Scripts\python.exe -m scripts.evaluate --top-k 2
.\.venv\Scripts\python.exe -m scripts.evaluate --top-k 20

# What do big chunks cost?
#   Set CHUNK_TARGET_TOKENS = 1000, rebuild, compare multihop recall.
.\.venv\Scripts\python.exe -m scripts.index --stats
.\.venv\Scripts\python.exe -m scripts.evaluate --retrieval-only
```

Note which of these need a rebuild and which don't: anything touching chunking or
the embedding model changes the *index*; anything touching queries, top_k, or
prompts does not.

## Git

```powershell
git status
git add -A
git commit -m "message"
git push
```

Repo: https://github.com/Dev23-R/Understanding-RAG (private)
