# wiki_agent

A question-answering agent on the **raw Anthropic SDK** + the **live MediaWiki API**. Phase 1: the
agent vertical slice (tool + manual tool-use loop + CLI + no-key contract selftest). The eval suite
is Phase 2.

> Status: Phase 1, under construction. This README is finalized at the last milestone.

## Quickstart
```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then put your real key in .env

python selftest.py            # live retrieval contract check — no API key needed
python -m cli.main "When was Alan Turing born?"
```

## Layout
- `agents/` — all agent code (`wikipedia.py` tool, `agent.py` loop, `prompts.py` placeholders).
- `cli/` — command-line demo (`python -m cli.main`).
- `selftest.py` — no-key live test of the retrieval contract.
