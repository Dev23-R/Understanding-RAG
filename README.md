# Understanding RAG

A hands-on project to understand how Retrieval-Augmented Generation (RAG) changes the
quality of an LLM's output — measured, not assumed.

## Goal

Build a working RAG pipeline over a corpus the model doesn't already know, then compare
answers **with** and **without** retrieval on the same questions, so the improvement is
observable rather than anecdotal.

## Planned structure

```
corpus/      source documents to index
src/         ingestion, chunking, embedding, retrieval, generation
evals/       question set + side-by-side baseline vs. RAG comparisons
notes/       findings as the project progresses
```

## Status

Scaffolding. Nothing implemented yet.
