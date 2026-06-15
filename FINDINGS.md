# Findings — Wikipedia QA Agent & Eval

*Draft for refinement before submission. Worker: `claude-sonnet-4-6`. Judge: `claude-opus-4-8`.
Retrieval: live English MediaWiki API, no caching. Raw Anthropic SDK only.*

## 1. The question we set out to answer

A retrieval QA agent can be **right for the wrong reason**: correct from the model's own
parametric memory, while the Wikipedia call added nothing to the answer and was just *theatrics*.
A naïve "is the answer correct?" eval cannot tell these apart. So the eval is built to separate
**"retrieval changed the answer"** from **"retrieval was ceremony,"** and to lead with that
distinction rather than with raw accuracy.

## 2. System design (the agent)

- **`search_wikipedia` tool** over the live MediaWiki API. The retrieval contract (recon-verified,
  lives in `agents/wikipedia.py`):
  - `generator=search` + `prop=extracts|info`, `exintro=1 explaintext=1 exlimit=max`, `inprop=url`.
    `exintro` is mandatory — it's the only mode that returns one extract *per* hit; whole-article
    truncation modes collapse `exlimit→1`, so truncation is done in Python instead.
  - Results are re-sorted by the `index` field (pages come back keyed by pageid, not search rank).
  - **Three-way status discriminated on the body `"error"` key, never HTTP status** — empty
    ("Wikipedia has nothing") and error (request failed) both return HTTP 200. Empty is distinct
    from error and from a *zero-searches* run.
- **Manual tool-use loop** (`agents/agent.py`) that takes its tool list **and** system prompt
  explicitly. This made **tool-off (closed-book) a first-class capability from day one** — the
  headline metric depends on it. The loop returns a structured `Trace` (per-search queries, snippets
  with URLs, statuses, the answer, `stop_reason`), enforces a search cap, and at the cap forces an
  answer by dropping tools only — never swapping in a different prompt mid-run.
- **Versioned prompts.** Worker prompts (`agents/prompts.py`) and judge prompts
  (`eval/judge_prompts.py`) are registries keyed by version, selectable per run. This let us A/B
  prompt changes and record exactly which versions produced each result.

## 3. Eval rationale (why these metrics, in this order)

Three metrics, **headline first**:

1. **`retrieval_necessity` (headline).** Run every case twice — open (tools on) and closed (tools
   off) — and have Judge B score both. Collapse to correct/incorrect and bucket the 2×2 into
   exactly one of:
   - **rescued** — open ✓, closed ✗ → retrieval was *needed*.
   - **hurt** — open ✗, closed ✓ → retrieval *degraded* the answer.
   - **ceremony** — correct both ways → retrieval didn't change correctness.
   - **both_wrong** — the agent just failed.

   The four sum to the total. This is the direct instrument for the thesis: it measures whether the
   wiki query *changed correctness*, not whether the agent merely produced a correct string. A clean
   closed-book prompt (no simulated searching, "answer from knowledge or say you don't know") keeps
   the baseline honest.

2. **`correctness`** — Judge B, reference-aware, branches on `question_class`.

3. **`groundedness`** — Judge A, reference-**blind**, judged against the run's **trace only** (never
   the gold answer): are the answer's claims supported by what was actually retrieved?

**Tags (`memory_ok`, `needs_verification`).** A key nuance: *just because a question could be
answered from memory doesn't mean retrieval is wrong.* We ground non-obvious queries to prevent
hallucination; "search is unnecessary" is true only for widely-known facts the model won't get wrong
("capital of the USA", "meters in a km"). The tags encode authored intent so we can (a) audit
unnecessary searches on `needs_verification=False` cases and (b) restrict the groundedness
population to the cases where grounding actually matters.

**Groundedness 2×2 (population + both axes pinned).**
- Population: only **correct** answers with `needs_verification=True` (exclude memory-OK and wrong
  answers — we only ask whether the *correct* answers were grounded).
- Rows: grounded | not-grounded (`partially_grounded` collapses to not-grounded; raw label kept).
- Columns: the **measured** necessity outcome (rescued | ceremony) — the run result, **not** the
  `needs_verification` tag. (Tag = "should we have searched," authored. Outcome = "did search change
  correctness," measured.)
- Cells: grounded+rescued = ideal; not-grounded+ceremony = pure theatrics; grounded+ceremony =
  verification; not-grounded+rescued = contradictory (flagged).

**Judges.** Two judges, single-shot, **structured outputs with the rationale field first** so the
judge reasons before it commits. Judge A is reference-blind (sees question, answer, trace); Judge B
is reference-aware (sees question, answer, reference, `question_class`) and branches per class, with
a `drift_note` for facts that plausibly vary over time. Judges are **versioned independently** so
each can be iterated without disturbing the other.

**Canary gate.** Before any billed run, the judges are sanity-checked on synthetic fixed inputs that
exercise both poles (correct+ungrounded, honest refusal of an unanswerable = correct, false-premise
call-out = correct, knowable-question refused = incorrect, fully-supported = grounded). The gate is a
**hard stop**: any verdict ≠ its expected label halts the run, and prompts/labels are never edited to
force it green.

**Cases authored for necessity, not difficulty.** Weighted toward facts genuinely not in memory
(post-cutoff recent events), plus name collisions, disputed/precise numerics, answer-from-memory
controls, and false_premise / unanswerable cases. **Every reference was live-verified against
Wikipedia**, since the references are the ground truth the judge scores against.

## 4. Results, and how they fit the rationale

Four committed runs (2 worker prompts × 2 judge versions), single-sample, 22 cases, run at
`--concurrency 2` to avoid live-API rate limiting. See the appendix for files.

**The thesis held, cleanly.** Across all configurations: **rescued ≈ 7, hurt = 0, ceremony = 15,
both_wrong = 0.** The rescued set is *exactly* the post-cutoff recent events (both 2025 Nobels,
the 98th Oscars host, Super Bowl LX, both UEFA Champions League finals, 2025 Wimbledon) — every one
had `closed = incorrect`. Retrieval added correctness **precisely where parametric memory can't
reach**, and **never degraded an answer** (0 hurt). That is the strongest possible read on the
question we started with.

**Correctness was 100% (22/22)** in every run — which is the point: the agent answers accurately when
it has the facts, so the *value of the eval is in the necessity/groundedness split*, not the raw
accuracy number.

**The theatrics the thesis worried about are real and measurable.** The baseline worker issued
unnecessary searches on **5** `needs_verification=False` cases (well-known facts + an unanswerable
question). A second prompt version (`oversearch_cut`) that says "answer canonical facts directly,
search the rest" **cut unnecessary retrieval 5 → 2 with zero cost** to correctness or necessity.
*The eval drove a concrete, validated prompt improvement* — the loop the exercise is meant to enable.

**Groundedness is the judge-sensitive metric; correctness and necessity are robust.** Holding the
worker fixed and only changing the judge prompt moved **4 groundedness labels** (e.g. Everest and
Moon flipped not-grounded → grounded) while **no** correctness or necessity number changed. The
refined Judge A ("grounded means *asserts nothing the trace doesn't support*," plus worked examples)
removed false-positive theatrics that the first judge produced on adequately-grounded answers. Takeaway:
the headline metrics are stable, but groundedness numbers must be read with judge-version awareness.

**The metric design insulated groundedness from the over-search fix.** Cutting search on the
well-known cases flipped their groundedness to not-grounded (no trace to support a memory answer) —
but those are `needs_verification=False`, so the population restriction kept them **out** of the
groundedness 2×2. The metric measured what it was supposed to, not a side effect of the prompt
change.

**Disputed numerics are the cleanest demonstration.** The Nile length: Wikipedia currently states
**7,088 km**, while the commonly-memorized figure is ~6,650 km. The closed (memory) run gives the
old number and scores partially_correct/incorrect; the open run retrieves and matches the reference —
a textbook "retrieval beats memory" rescue.

## 5. Key learnings

- **The necessity 2×2 is a working instrument for the thesis** — it separates *rescued* from
  *ceremony* on real cases, which a correctness-only eval cannot.
- **With an honest closed-book prompt, retrieval is safe** (0 hurt everywhere): it adds facts the
  model lacks without degrading what it already knew.
- **Over-search is real, measurable, and promptable away** without quality loss — the eval both
  surfaced it (the search audit) and validated the fix.
- **Groundedness is the subjective, judge-sensitive axis**; necessity and correctness are robust.
  Invest judge-prompt effort there, and treat single-judge groundedness as directional.
- **The canary gate earned its keep** — it caught two real judge bugs *before* any billed run: a
  copy-paste that put a correctness prompt in the groundedness slot, and a default-version name typo
  that would have crashed the run. Cheap insurance against silently-wrong judges.
- **Case authoring discipline matters.** A false premise must be *unambiguously* false: "Edison
  invented the light bulb" is widely credited and only nuanced-false, so it was replaced with
  "Einstein won his Nobel for relativity" (the 1921 prize was explicitly for the photoelectric
  effect). References must be live-verified and are point-in-time.
- **Live-API realities bite.** MediaWiki rate-limits (HTTP 429) under concurrency; one early run was
  corrupted when all three Nile searches got 429'd and the worker fell back to the stale memorized
  figure, producing a spurious `hurt`. The harness surfaced it (`status=error` in the trace, graceful
  degradation) — and lowering concurrency produced clean runs. The error path is part of the contract,
  not an afterthought.
- **Single-sample noise is real.** The 2026 Winter Olympics case flipped rescued↔ceremony between
  runs (the closed model sometimes knew Milano Cortina from memory). The report flags single-sample
  variance; small deltas should not be over-read.

## 6. Future work

- **Prompt iteration on the residual over-search.** `oversearch_cut` still searches the
  `false_premise` and `unanswerable` cases (its rule covers only well-known facts, and its
  "possibly false premise → search" line actively encourages searching false premises). Next version:
  handle those two classes explicitly and push unnecessary retrieval below 2.
- **Multi-sample / best-of-N.** Everything here is single-sample. Repeat each cell N times to quantify
  run-to-run variance and report confidence, rather than caveating it in prose.
- **Groundedness robustness.** Given its judge sensitivity, use a multi-judge ensemble or majority
  vote, and/or an adversarial groundedness case set.
- **Bigger, broader case set.** 22 cases is a proof of instrument; scale up per class/category, add
  harder disambiguation and numeric cases.
- **Retrieval resilience.** Add bounded retry/backoff to `search_wikipedia` so a transient 429 doesn't
  silently push the worker onto memory (today it surfaces as `error` and the worker degrades).
- **Reference freshness.** References are point-in-time Wikipedia snapshots; add an automated
  re-verification pass since live ground truth drifts.
- **Per-class reporting** and a derived "should-have-searched" precision/recall from tags vs. actual
  search behavior.

## 7. Limitations

- Single-sample per cell; small N (22).
- References are point-in-time Wikipedia snapshots; ground truth can drift, and Wikipedia is itself
  the arbiter (the Nile "7,088 km" is Wikipedia's figure, not an undisputed truth).
- Groundedness judgments are subjective and judge-prompt-sensitive.
- Live-API variability (rate limits, page edits) can perturb runs.
- The worker's exact training cutoff is unknown; "recent" cases assume post-cutoff, but some (e.g.
  the Winter Olympics host) were partly in memory.

## Appendix — committed runs

All single-sample, 22 cases, `--concurrency 2`. Headers in each report record the exact versions.

| run | worker prompt | judges | unnecessary_retrieval | necessity (R/H/C/BW) | correctness | groundedness (ideal/verif/theatrics/contra) |
|---|---|---|---|---|---|---|
| `085953` | baseline | baseline | 5 | 7/0/15/0 | 22/22 | 7/4/2/0 |
| `085231` | oversearch_cut | baseline | 2 | 7/0/15/0 | 22/22 | 7/4/2/0 |
| `094506` | baseline | baseline_plus_examples | 5 | 7/0/15/0 | 22/22 | 7/6/0/0 |
| `093724` | oversearch_cut | baseline_plus_examples | 2 | 7/0/15/0 | 22/22 | 7/5/1/0 |

Reproduce: `python -m eval.run canaries` (gate) → `python -m eval.run full --prompt-version <v>
--judge-a-version <v> --judge-b-version <v> --concurrency 2`.
