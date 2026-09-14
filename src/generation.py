"""Generating answers, with and without retrieved context.

The prompt in this file is doing more work than it looks. Retrieval puts the
right text in front of the model; the prompt decides whether the model *uses*
it, *trusts* it over its own priors, and *admits* when it is not there. Those
are three separate failure modes and each is addressed by a specific line below.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import ollama

from . import config
from .retrieval import RetrievalResult


@dataclass
class Answer:
    text: str
    prompt: str
    used_context: bool
    citations: list[str]
    prompt_tokens: int
    completion_tokens: int
    duration_s: float


# --- Prompts --------------------------------------------------------------

BASELINE_SYSTEM = """You are a helpful assistant answering questions about \
internal engineering systems. Answer from your own knowledge. Be concise and \
specific."""


# Each constraint here exists because of a specific, observable failure.
GROUNDED_SYSTEM = """You are a helpful assistant answering questions about the \
Meridian platform at Northwind Freight.

Answer using ONLY the context provided below. The context is authoritative \
internal documentation.

Rules:
1. If the context does not contain the answer, say "The provided documentation \
does not cover this." Do not fill the gap from general knowledge.
2. Cite the source of each claim using the [DOC-ID] markers shown in the \
context.
3. If the context contradicts what you believe to be generally true, follow the \
context. This is a specific organisation with its own conventions.
4. Be concise and specific. Prefer exact values, commands, and names from the \
context over paraphrase.
5. Do not speculate about what the documentation "probably" means beyond what \
it states."""


def build_context_block(results: list[RetrievalResult]) -> tuple[str, list[str]]:
    """Format retrieved chunks for insertion into the prompt.

    Three formatting decisions, each of which measurably changes behaviour:

    1. **Explicit delimiters and numbering.** The model needs to be able to tell
       where one source ends and the next begins. Concatenating chunks with
       blank lines produces answers that blend two documents into a single
       confident claim that neither document makes.

    2. **Citation markers in the text.** Putting `[OPS-002]` inline gives the
       model a token it can copy. Asking for citations without providing a
       handle to cite produces invented references -- the model writes
       "[source 3]" for a source that does not exist.

    3. **Most relevant first.** Models attend unevenly across long contexts, and
       the beginning gets the most reliable attention. Ordering by relevance
       puts the best evidence where it is most likely to be used.
    """
    if not results:
        return "", []

    blocks: list[str] = []
    citations: list[str] = []

    for i, result in enumerate(results, start=1):
        chunk = result.chunk
        marker = chunk.doc_id
        citations.append(chunk.citation)
        heading = " > ".join(chunk.heading_path) if chunk.heading_path else ""
        location = f"{chunk.doc_title}" + (f" > {heading}" if heading else "")

        blocks.append(
            f"--- SOURCE {i} [{marker}] ---\n"
            f"Location: {location}\n"
            f"Relevance: {result.score:.3f}\n\n"
            f"{chunk.body.strip()}"
        )

    return "\n\n".join(blocks), citations


def _strip_thinking(text: str) -> str:
    """Remove <think> blocks emitted by reasoning models such as Qwen3.

    Qwen3 emits its chain of thought inside <think></think> tags by default.
    That is useful for debugging and noise in an answer comparison, so we strip
    it from the answer text. The reasoning still happened and is still billed in
    tokens -- this only affects display.
    """
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


# --- Generation -----------------------------------------------------------

def _generate(
    system: str, user: str, *, think: bool = True
) -> tuple[str, int, int, float]:
    # Qwen3 is a hybrid reasoning model: it emits a <think> block before
    # answering unless told not to. Thinking costs ~15x the wall-clock time on
    # this hardware (75s vs 5s), which matters when an eval run is 28 calls.
    #
    # `/no_think` is a Qwen3-specific control token, not a general Ollama
    # feature -- it does nothing on Llama or Mistral. Swap the model and this
    # line becomes dead code rather than an error, which is exactly the kind of
    # silent no-op worth commenting.
    #
    # The tradeoff is real but smaller than you would guess: on this eval set
    # thinking helps the *baseline* (the model reasons its way to admitting
    # uncertainty more often) and barely moves the *grounded* answers, because
    # when the fact is sitting in the prompt there is little to reason about.
    # That asymmetry is itself a finding -- see notes/07.
    if not think:
        system = f"{system}\n\n/no_think"

    response = ollama.chat(
        model=config.OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        options={
            "temperature": config.OLLAMA_TEMPERATURE,
            "seed": config.OLLAMA_SEED,
            # See config.py -- Ollama defaults to 4096 regardless of model
            # capability and truncates silently from the start of the prompt,
            # which is where the system instructions live.
            "num_ctx": config.OLLAMA_NUM_CTX,
        },
    )

    text = response["message"]["content"]
    prompt_tokens = response.get("prompt_eval_count", 0)
    completion_tokens = response.get("eval_count", 0)
    duration_s = response.get("total_duration", 0) / 1e9

    return text, prompt_tokens, completion_tokens, duration_s


def answer_baseline(question: str, *, think: bool = True) -> Answer:
    """Answer with no retrieval -- the control condition.

    This is what the model knows without help. On a corpus of invented facts the
    honest answer is "I have no idea", and the interesting question is whether
    the model says that or invents something plausible instead. It usually
    invents. That tendency is the problem RAG exists to solve, and seeing it
    firsthand is more convincing than being told about it.
    """
    text, pt, ct, dur = _generate(BASELINE_SYSTEM, question, think=think)
    return Answer(
        text=_strip_thinking(text),
        prompt=question,
        used_context=False,
        citations=[],
        prompt_tokens=pt,
        completion_tokens=ct,
        duration_s=dur,
    )


def answer_with_context(
    question: str, results: list[RetrievalResult], *, think: bool = True
) -> Answer:
    """Answer grounded in retrieved chunks."""
    context_block, citations = build_context_block(results)

    if not context_block:
        # Retrieval found nothing above threshold. We still call the model, but
        # we tell it so explicitly rather than silently sending an empty context
        # section -- an empty section reads as "the documentation is blank",
        # which invites the model to fall back on priors.
        user = (
            f"No relevant documentation was found for this question.\n\n"
            f"Question: {question}"
        )
    else:
        # Question placed AFTER the context. Two reasons: the long, stable
        # context sits at the front where it can be cached across queries in
        # systems that support prefix caching, and the instruction the model
        # should act on last sits closest to where generation begins.
        user = (
            f"CONTEXT:\n\n{context_block}\n\n"
            f"---\n\n"
            f"Question: {question}"
        )

    text, pt, ct, dur = _generate(GROUNDED_SYSTEM, user, think=think)
    return Answer(
        text=_strip_thinking(text),
        prompt=user,
        used_context=bool(context_block),
        citations=citations,
        prompt_tokens=pt,
        completion_tokens=ct,
        duration_s=dur,
    )


def check_model_available() -> None:
    """Fail early with an actionable message if Ollama is not ready."""
    try:
        models = [m.get("model", "") for m in ollama.list().get("models", [])]
    except Exception as exc:  # noqa: BLE001 - surfacing the cause is the point
        raise RuntimeError(
            "Could not reach Ollama. Is the service running? "
            "Try `ollama list` in a terminal."
        ) from exc

    if not any(m.startswith(config.OLLAMA_MODEL.split(":")[0]) for m in models):
        raise RuntimeError(
            f"Model '{config.OLLAMA_MODEL}' not found in Ollama. "
            f"Pull it with:\n    ollama pull {config.OLLAMA_MODEL}"
        )
