"""CLI demo for the Wikipedia QA agent.

    python -m cli.main "When was Alan Turing born?"
    python -m cli.main "..." --verbose      # full trace: queries + snippets
    python -m cli.main "..." --no-tools      # closed-book run (retrieval_necessity baseline)

Prints the answer and whether search was used; the full trace shows only with --verbose.
"""
from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

from agents.agent import WORKER_MODEL, run_agent
from agents.prompts import WORKER_SYSTEM_PROMPT_CLOSED, WORKER_SYSTEM_PROMPT_OPEN
from agents.wikipedia import SEARCH_WIKIPEDIA_TOOL


def main() -> int:
    parser = argparse.ArgumentParser(description="Ask the Wikipedia QA agent a question.")
    parser.add_argument("question", help="the question to answer")
    parser.add_argument("--no-tools", action="store_true",
                        help="closed-book run with no retrieval (retrieval_necessity baseline)")
    parser.add_argument("--verbose", action="store_true",
                        help="print the full trace: each query, status, and snippet")
    parser.add_argument("--model", default=WORKER_MODEL, help=f"worker model (default: {WORKER_MODEL})")
    args = parser.parse_args()

    load_dotenv()

    if args.no_tools:
        system_prompt, prompt_name, tools = WORKER_SYSTEM_PROMPT_CLOSED, "WORKER_SYSTEM_PROMPT_CLOSED", []
    else:
        system_prompt, prompt_name, tools = WORKER_SYSTEM_PROMPT_OPEN, "WORKER_SYSTEM_PROMPT_OPEN", [SEARCH_WIKIPEDIA_TOOL]

    if not system_prompt.strip():
        print(f"error: {prompt_name} is empty — author it in agents/prompts.py first.", file=sys.stderr)
        return 2
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: ANTHROPIC_API_KEY not set (put it in .env).", file=sys.stderr)
        return 2

    import anthropic
    client = anthropic.Anthropic()
    trace = run_agent(args.question, tools=tools, system_prompt=system_prompt,
                      client=client, model=args.model)

    print(trace.answer or "(no answer produced)")
    print()
    print(_search_summary(trace))

    if args.verbose:
        _print_trace(trace)
    return 0


def _search_summary(trace) -> str:
    if not trace.tool_enabled:
        return "Search used: no (closed-book run)"
    if trace.search_count == 0:
        return "Search used: no (tool available; worker answered from memory)"
    plural = "search" if trace.search_count == 1 else "searches"
    return f"Search used: yes — {trace.search_count} {plural} (stop: {trace.stop_reason})"


def _print_trace(trace) -> None:
    print("\n=== trace ===")
    if not trace.searches:
        print("(no searches)")
    for i, s in enumerate(trace.searches, 1):
        print(f"\n[search {i}] query={s.query!r}  status={s.status}")
        if s.status == "error":
            print(f"    error: {s.error}")
        for j, snip in enumerate(s.results, 1):
            print(f"    ({j}) {snip.title} — {snip.url}")
            for line in snip.extract.splitlines():
                print(f"        {line}")


if __name__ == "__main__":
    sys.exit(main())
