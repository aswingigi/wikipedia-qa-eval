"""Judge output schemas (mine) and judge calls. Prompt TEXT comes from eval.judge_prompts (yours).

Structured outputs via client.messages.parse(..., output_format=<pydantic>). The rationale field is
FIRST in each schema so the model generates it before the verdict — i.e. reasons before committing.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

JUDGE_MODEL = "claude-opus-4-8"
_MAX_TOKENS = 1024


class GroundednessVerdict(BaseModel):
    rationale: str
    groundedness: Literal["grounded", "partially_grounded", "not_grounded"]
    unsupported_claims: list[str]


class CorrectnessVerdict(BaseModel):
    correctness_rationale: str
    correctness: Literal["correct", "partially_correct", "incorrect"]
    drift_note: str  # "" when not applicable; set when the answer contradicts a plausibly-time-varying reference fact


def render_trace(trace) -> str:
    """Render an open-run Trace's retrieved content as Judge A's only evidence (reference-blind)."""
    if not trace.searches:
        return "(no searches were performed)"
    parts = []
    for i, s in enumerate(trace.searches, 1):
        parts.append(f"Search {i}: query={s.query!r} status={s.status}")
        if s.status == "error":
            parts.append(f"  error: {s.error}")
        for j, snip in enumerate(s.results, 1):
            parts.append(f"  [{j}] {snip.title} — {snip.url}\n{snip.extract}")
    return "\n".join(parts)


def run_judge_a(client, *, question: str, answer: str, trace, prompt: str) -> GroundednessVerdict:
    """Groundedness, reference-blind: are the answer's claims supported by what was retrieved?"""
    content = (
        f"Question:\n{question}\n\n"
        f"Answer:\n{answer}\n\n"
        f"Retrieved Wikipedia content (the only evidence available to you):\n{render_trace(trace)}"
    )
    verdict = client.messages.parse(
        model=JUDGE_MODEL, max_tokens=_MAX_TOKENS, system=prompt,
        messages=[{"role": "user", "content": content}],
        output_format=GroundednessVerdict,
    ).parsed_output
    if verdict is None:
        raise RuntimeError("Judge A returned no parsed output")
    return verdict


def run_judge_b(client, *, question: str, answer: str, reference: str, question_class: str, prompt: str) -> CorrectnessVerdict:
    """Correctness, reference-aware: is the answer accurate against the reference (per question_class)?"""
    content = (
        f"Question:\n{question}\n\n"
        f"Question class: {question_class}\n\n"
        f"Candidate answer:\n{answer}\n\n"
        f"Reference (ground truth):\n{reference}"
    )
    verdict = client.messages.parse(
        model=JUDGE_MODEL, max_tokens=_MAX_TOKENS, system=prompt,
        messages=[{"role": "user", "content": content}],
        output_format=CorrectnessVerdict,
    ).parsed_output
    if verdict is None:
        raise RuntimeError("Judge B returned no parsed output")
    return verdict
