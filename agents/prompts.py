"""Worker system prompts — AUTHORED BY YOU, and versioned so you can A/B as you iterate.

Each entry in WORKER_PROMPTS is a named version holding an open-book prompt (the worker has
the search_wikipedia tool) and a closed-book prompt (tools off — the retrieval_necessity
baseline). Add a new entry per iteration; select one with `--prompt-version` (CLI) or
get_prompt(version, open_book=...) (Phase-2 eval, which can also sweep available_versions()).

The agent loop takes the system prompt explicitly and, at the search cap, reuses whichever
prompt it was given — it never swaps the closed-book prompt in mid-run.

Tip: reuse BASELINE_CLOSED for the closed-book text across versions to keep a fixed
retrieval_necessity baseline; override it per version only when you mean to.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptVersion:
    open: str    # open-book: search_wikipedia available
    closed: str  # closed-book: tools off (retrieval_necessity baseline)


# Closed-book baseline. Reuse across versions for a stable necessity baseline.
BASELINE_CLOSED = "You are a helpful assistant that answers general-knowledge questions. Answer the user's question clearly and concisely."

WORKER_PROMPTS: dict[str, PromptVersion] = {
    "baseline": PromptVersion(
        open="You are a helpful assistant that answers general-knowledge questions. You have a search_wikipedia tool available if you want to look something up. Answer the user's question clearly and concisely.",
        closed=BASELINE_CLOSED,
    ),
    # Add iterations here, e.g.:
    # "v2": PromptVersion(open="...improved open-book prompt...", closed=BASELINE_CLOSED),
}

DEFAULT_VERSION = "baseline"


def available_versions() -> list[str]:
    return list(WORKER_PROMPTS)


def get_prompt(version: str, *, open_book: bool) -> str:
    """Return the open- or closed-book prompt for a named version. Raises KeyError if unknown."""
    try:
        pv = WORKER_PROMPTS[version]
    except KeyError:
        raise KeyError(f"unknown prompt version {version!r}; available: {', '.join(WORKER_PROMPTS)}")
    return pv.open if open_book else pv.closed
