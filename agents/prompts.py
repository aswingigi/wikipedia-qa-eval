"""Worker system prompts — AUTHORED BY YOU.

These two constants are intentionally empty placeholders. Fill them in; the agent loop
imports them and the CLI refuses to run until the one it needs is non-empty.

The loop takes the system prompt explicitly, so the open-book and closed-book runs use
the two different prompts you control here. At the search cap the loop reuses whichever
prompt it was given — it never swaps the closed-book prompt in mid-run.
"""

# Open-book: the worker has the search_wikipedia tool available.
WORKER_SYSTEM_PROMPT_OPEN = ""  # TODO: you author this

# Closed-book: tools disabled — the retrieval_necessity baseline (Phase 2).
WORKER_SYSTEM_PROMPT_CLOSED = ""  # TODO: you author this
