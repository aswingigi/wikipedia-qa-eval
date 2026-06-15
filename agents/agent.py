"""Manual tool-use loop for the Wikipedia QA worker.

The loop takes its tool list AND its system prompt explicitly, so the same code path
serves both runs the Phase-2 eval needs:
  - open-book : run_agent(..., tools=[SEARCH_WIKIPEDIA_TOOL], system_prompt=OPEN)
  - closed-book (retrieval_necessity baseline): run_agent(..., tools=[], system_prompt=CLOSED)

It returns a structured Trace — the contract the eval scores later. At the search cap
the loop forces a final answer by dropping tools ONLY; the system prompt it was given
is reused unchanged (an open-book run that hits the cap stays open-book — we never swap
in the closed-book prompt mid-run). The loop never raises on the answer path.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from agents.wikipedia import SEARCH_WIKIPEDIA_TOOL, SearchResult, render_result, search_wikipedia

WORKER_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 2048
_DEFAULT_MAX_SEARCHES = 5


@dataclass
class Trace:
    question: str
    answer: str
    searches: list[SearchResult] = field(default_factory=list)
    stop_reason: str = "voluntary"  # "voluntary" | "cap_hit"
    tool_enabled: bool = False

    @property
    def search_count(self) -> int:
        return len(self.searches)


def run_agent(
    question: str,
    *,
    tools: list[dict],
    system_prompt: str,
    client,
    model: str = WORKER_MODEL,
    max_searches: int = _DEFAULT_MAX_SEARCHES,
    max_tokens: int = _MAX_TOKENS,
) -> Trace:
    """Drive the worker to an answer. `tools=[]` runs closed-book. See module docstring."""
    tool_enabled = bool(tools)
    searches: list[SearchResult] = []
    messages: list[dict] = [{"role": "user", "content": question}]

    while True:
        offer_tools = tools if (tool_enabled and len(searches) < max_searches) else None
        resp = _create(client, model, system_prompt, messages, offer_tools, max_tokens)
        messages.append({"role": "assistant", "content": resp.content})

        tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
        if resp.stop_reason == "tool_use" and tool_uses:
            tool_results = []
            for tu in tool_uses:
                query = tu.input.get("query", "") if isinstance(tu.input, dict) else ""
                result = search_wikipedia(query)
                searches.append(result)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": render_result(result),
                    "is_error": result.is_error,
                })
            messages.append({"role": "user", "content": tool_results})

            if len(searches) >= max_searches:
                # Cap reached: force the final answer. Drop tools ONLY; keep the same
                # system prompt the caller gave us (do NOT switch to a closed-book prompt).
                messages.append({
                    "role": "user",
                    "content": (
                        "You have reached the search limit and cannot search again. "
                        "Answer the question now using the information you have gathered."
                    ),
                })
                final = _create(client, model, system_prompt, messages, None, max_tokens)
                return Trace(
                    question=question,
                    answer=_extract_text(final),
                    searches=searches,
                    stop_reason="cap_hit",
                    tool_enabled=tool_enabled,
                )
            continue

        # Natural stop (end_turn / max_tokens / ...): the worker has answered.
        return Trace(
            question=question,
            answer=_extract_text(resp),
            searches=searches,
            stop_reason="voluntary",
            tool_enabled=tool_enabled,
        )


def _create(client, model, system_prompt, messages, tools, max_tokens):
    kwargs = dict(model=model, max_tokens=max_tokens, system=system_prompt, messages=messages)
    if tools:
        kwargs["tools"] = tools
    return client.messages.create(**kwargs)


def _extract_text(resp) -> str:
    """Concatenate text blocks; returns "" if there are none. Never raises."""
    return "".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    ).strip()


# Re-export so callers can build the open-book tool list without importing wikipedia too.
__all__ = ["Trace", "run_agent", "WORKER_MODEL", "SEARCH_WIKIPEDIA_TOOL"]
