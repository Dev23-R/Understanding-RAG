---
tags: [finding, evaluation, results]
---

# Eval Results

Run `20260914T095854Z-hybrid-k5` · 14 questions · 53 chunks · hybrid retrieval ·
top_k=5 · `qwen3:8b` · thinking off · temperature 0.0, seed 42.

## Headline

| | Baseline | RAG |
|---|---:|---:|
| Correct | **2/14 (14%)** | **14/14 (100%)** |
| Mean prompt tokens | 54 | 1,234 |

**+86 percentage points for ~23x the prompt tokens.**

## By category

| Category | n | Baseline | RAG |
|---|---:|---:|---:|
| `lookup` | 6 | 1 | 6 |
| `multihop` | 4 | 1 | 4 |
| `collision` | 2 | 0 | 2 |
| `absent` | 2 | 0 | 2 |

## The two baseline passes were lucky guesses

This is the detail that makes the headline number meaningful rather than
impressive-sounding.

**q05 — "Can I deploy to production on a Friday?"** The baseline said no.
Correct — but because "don't deploy on Friday" is widespread industry folk
wisdom, not because it knows Meridian's rule. It could not have told you the rule
exists, that exceptions require incident commander approval, or that security
patches are pre-approved.

**q07 — "Why two separate regional stacks?"** The baseline said GDPR. Also
correct, and also a guess: data residency is the usual reason any company splits
regions. It didn't know about `sibling_shipment_id`, or that the split was
explicitly *not* a performance decision.

So the baseline's real score on *knowing anything about Meridian* is **0/14**.
Both passes are cases where generic advice happened to coincide with specific
policy — which is exactly the kind of coincidence that makes ungrounded models
feel more reliable than they are.

## Retrieval quality

Mean recall **0.79** across all 14 questions; **1.00 on every answerable
question**. The `absent` questions score 0 by construction — they retrieve
something (there's always a least-bad chunk), and the definition of success for
them is retrieving nothing.

Strategy comparison (retrieval only):

| Strategy | Mean recall |
|---|---:|
| Dense | 0.79 |
| Lexical | 0.75 |
| Hybrid | 0.79 |

**Hybrid did not beat dense here, and that's a property of the benchmark, not of
hybrid retrieval.** 53 chunks across 8 well-separated topics leaves no headroom —
dense alone is already perfect on every answerable question. See
[[05 - Dense vs Lexical vs Hybrid]] for where the difference would show up.

## What had to be fixed to get here

Three real problems surfaced during the build. All three are more interesting
than the final number.

**1. A `datetime.date` crash on index save.** PyYAML parses
`last_reviewed: 2026-07-14` into a Python `date` object, which `json.dumps`
refuses. Fixed with `default=str`. Mundane, but a reminder that frontmatter
parsing returns typed objects, not strings.

**2. A tokenizer warning that was a false alarm.** `Token indices sequence length
is longer than the specified maximum (843 > 512)` looked like silent truncation.
It wasn't — `count_tokens` measures whole document sections to decide how to
split them, and that string is never embedded. Suppressed deliberately, because
a scary-but-meaningless warning teaches you to ignore your own logs, and the same
message from `embed_passages` *would* mean real data loss.

**3. A false failure in the eval itself.** q11 was graded as failing while giving
a correct answer. See [[08 - Measuring Whether Any Of This Worked]] — substring
matching can't handle negation. This one matters most: **a false failure you
don't investigate sends you optimising against a bug in your ruler.**

## Two eval-design errors worth recording

**q14 was miscategorised.** *"What is the SLA of the Vantage Compliance API?"*
was marked `absent`. It isn't — the corpus explicitly states Vantage has no SLA.
A *documented absence* is not the same as *absent information*, and the correct
answer is "there isn't one", not "the documentation does not cover this". Worth
distinguishing, because a system tuned only to avoid hallucination starts
declining questions it can answer, and over-refusal is its own failure mode.

**q11's grader forbade vocabulary instead of an assertion.** Now
`["Atlas is a database", "Atlas is MongoDB"]` rather than `["MongoDB"]`.

## Caveats — read these before quoting the number

- **The corpus is tiny.** 53 chunks. Retrieval is easy at this scale in a way it
  is not at 50,000 chunks.
- **The corpus is fully invented**, so the baseline is guaranteed to fail. That's
  what makes the experiment *clean*, and also what makes 14% a floor rather than
  a realistic baseline for a real corpus where the model knows something.
- **Grading is substring matching.** Sufficient for exact facts, blind to
  fluency, completeness, and negation.
- **One model, one corpus, one run.** Seeded and deterministic, but not a
  statement about RAG in general.

The right reading: *on questions about information a model cannot have, retrieval
is the difference between confident invention and correct answers.* Not: *RAG
gives you +86 points.*

Related: [[The Atlas Hallucination]] · [[Similarity Thresholds Do Not Separate]] ·
[[08 - Measuring Whether Any Of This Worked]]
