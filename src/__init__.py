"""Meridian RAG — a teaching implementation of retrieval-augmented generation.

Module map, in pipeline order:

    config      every tunable, in one place
    corpus      loading documents off disk
    chunking    splitting documents into retrievable units
    embedding   text -> vectors (and the query/passage asymmetry)
    store       the vector index: one matrix multiply and an argsort
    retrieval   dense, lexical, and hybrid search
    generation  prompting the model, with and without context

Each module's docstring explains the design decisions it makes and why. The
accompanying notes in the Obsidian vault cover the concepts at a level above
the code.
"""
