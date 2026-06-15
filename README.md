# wiki_agent

A question-answering agent built on the **raw Anthropic SDK** + the **live MediaWiki API**
(no agent frameworks, no hosted search/RAG, no caching), plus an eval suite that measures whether
retrieval actually adds correctness. Two parts: the **agent** (`agents/`, `cli/`) and the **eval**
(`eval/`) with three metrics — `retrieval_necessity` (headline), `correctness`, `groundedness`.

- Worker model: `claude-sonnet-4-6` · Judge model: `claude-opus-4-8` (both verified live).

See **[FINDINGS.md](FINDINGS.md)** for the eval rationale, results, learnings, and future work.

## Setup
```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then put your real ANTHROPIC_API_KEY in .env
```

## Worker prompts (versioned)
The worker system prompts are **yours to write**, in `agents/prompts.py`, and they're versioned so
you can A/B as you iterate. `WORKER_PROMPTS` maps a version name to a `PromptVersion(open, closed)`:
an open-book prompt (the `search_wikipedia` tool is available) and a closed-book prompt (tools off;
the retrieval_necessity baseline). Versions `baseline` and `oversearch_cut` are provided — add new
entries as you iterate and select one with `--prompt-version`. The eval can sweep `available_versions()`.
The CLI refuses to run if the selected version's prompt is empty.

## Run
```sh
python -m cli.main "When was Alan Turing born?"      # open-book; prints answer + whether search was used
python -m cli.main "..." --verbose                    # also print the full trace (queries + snippets)
python -m cli.main "..." --no-tools                   # closed-book run (no retrieval)
python -m cli.main "..." --prompt-version oversearch_cut  # worker version: baseline | oversearch_cut (default)
```

## Selftest (no API key)
```sh
python selftest.py
```
Hits the live MediaWiki endpoint and asserts the retrieval **contract shape** — the three-way
status (`ok`/`empty`/`error`) and the trace fields (snippets carry title, `https://` URL, truncated
extract) — not article text, so a page edit won't make it flaky. A reviewer can run it without a key.

## Eval
Measures whether retrieval adds correctness, not just whether the agent answers. Three metrics:
- **retrieval_necessity** (headline): each case is run open (tools on) and closed (tools off); it
  lands in exactly one of rescued / hurt / ceremony / both_wrong.
- **correctness**: Judge B (reference-aware) vs a verified reference, branching on `question_class`.
- **groundedness**: Judge A (reference-blind) — are the answer's claims supported by what was retrieved?

You author the judge prompts (versioned, per judge) in `eval/judge_prompts.py`; cases (`eval/cases.py`)
and canaries (`eval/canaries.py`) are drafted for you to verify/edit.

```sh
# 1. Gate: run the canaries (real judges on synthetic inputs). Prints every verdict and stops.
python -m eval.run canaries
# 2. After the gate passes, run the full eval (billed; writes results/<runid>-report.md + -cases.json):
python -m eval.run full
# options: --prompt-version, --judge-a-version, --judge-b-version, --concurrency N (default 2)
# Concurrency defaults to 2 because the live MediaWiki API rate-limits (HTTP 429) under load;
# raise it only cautiously. Defaults: worker oversearch_cut, judges baseline_plus_examples.
```
The canary gate is a hard stop: if any verdict ≠ its expected label it reports and exits non-zero —
fix the judge prompt, never the expected label. Runs are single-sample (noise is noted in the report).

## Layout
```
agents/
  wikipedia.py   search_wikipedia tool. The full retrieval contract lives in its module docstring:
                 exact request, index re-sort, boundary-safe truncation, and how ok/empty/error are
                 resolved (on the body "error" key — never HTTP status; empty and error are both 200).
  agent.py       run_agent(question, *, tools, system_prompt, client, ...) -> Trace. Manual tool-use
                 loop, search cap. At the cap it forces a final answer by dropping tools only and
                 reusing the given prompt (recorded as stop_reason="cap_hit").
  prompts.py     versioned worker prompts (WORKER_PROMPTS registry) — you author these.
cli/
  main.py        the CLI demo (python -m cli.main).
eval/
  cases.py       eval cases (live-verified references) — you verify/edit.
  canaries.py    judge sanity-check cases + expected labels — you verify/edit.
  judge_prompts.py  per-judge versioned prompt registries — you author.
  judges.py      judge output schemas + calls (messages.parse on the judge model).
  metrics.py     necessity / correctness / groundedness aggregation.
  run.py         parallel orchestrator + canary gate (python -m eval.run canaries|full).
selftest.py      no-key live contract test.
results/         per-run report + per-case files (you commit the one you cite).
```

## The trace (what the eval scores)
`run_agent` returns a `Trace`: `question`, `answer`, `searches[]` (each with `query`, `status`, and
`results[]` of `title`/`url`/`extract`), `stop_reason` (`voluntary` | `cap_hit`), `search_count`, and
`tool_enabled`. A per-search `empty` (Wikipedia has nothing) is distinct from a zero-searches run
(`search_count == 0`, e.g. closed-book or a worker that answered from memory).

## Not in scope
Best-of-N / multi-sample eval, metrics beyond the three above, and any caching — decide these from
the results.
