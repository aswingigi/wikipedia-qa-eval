# wiki_agent

A question-answering agent built on the **raw Anthropic SDK** + the **live MediaWiki API**
(no agent frameworks, no hosted search/RAG, no caching). This is **Phase 1**: the agent vertical
slice. The eval suite (`retrieval_necessity` / `correctness` / `groundedness`) is Phase 2 and is
deliberately not built yet — but the loop already runs **tool-on or tool-off**, which the headline
`retrieval_necessity` metric depends on.

- Worker model: `claude-sonnet-4-6` · Judge model (Phase 2): `claude-opus-4-8` (both verified live).

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
the retrieval_necessity baseline). A `baseline` version is provided — add new entries as you improve
the prompt and select one with `--prompt-version`. The Phase-2 eval can sweep `available_versions()`.
The CLI refuses to run if the selected version's prompt is empty.

## Run
```sh
python -m cli.main "When was Alan Turing born?"      # open-book; prints answer + whether search was used
python -m cli.main "..." --verbose                    # also print the full trace (queries + snippets)
python -m cli.main "..." --no-tools                   # closed-book run (no retrieval)
python -m cli.main "..." --prompt-version baseline    # pick a worker prompt version (default: baseline)
```

## Selftest (no API key)
```sh
python selftest.py
```
Hits the live MediaWiki endpoint and asserts the retrieval **contract shape** — the three-way
status (`ok`/`empty`/`error`) and the trace fields (snippets carry title, `https://` URL, truncated
extract) — not article text, so a page edit won't make it flaky. A reviewer can run it without a key.

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
selftest.py      no-key live contract test.
```

## The trace (what Phase 2 will score)
`run_agent` returns a `Trace`: `question`, `answer`, `searches[]` (each with `query`, `status`, and
`results[]` of `title`/`url`/`extract`), `stop_reason` (`voluntary` | `cap_hit`), `search_count`, and
`tool_enabled`. A per-search `empty` (Wikipedia has nothing) is distinct from a zero-searches run
(`search_count == 0`, e.g. closed-book or a worker that answered from memory).

## Not in scope (Phase 2)
The eval suite and its three metrics, judge prompts, eval cases, and any caching.
