"""Judge canaries — I DRAFT the cases and expected labels; you verify/edit. You author the judge
prompts (I never do). The canaries are synthetic fixed inputs fed straight to the real judges (they
bypass the worker) to sanity-check judge behavior before any real run.

Coverage:
  - Judge A (groundedness): c1 (ungrounded pole) + c5 (grounded pole).
  - Judge B (correctness): c2 (honest refusal of unanswerable = correct), c3 (false premise called
    out = correct), c4 (knowable question refused = incorrect, the mirror of c2). c1 also = correct.
"""
from __future__ import annotations

from dataclasses import dataclass

from agents.agent import Trace
from agents.wikipedia import SearchResult, Snippet


@dataclass
class Canary:
    id: str
    question: str
    answer: str
    # Judge B (correctness):
    reference: str | None = None
    question_class: str | None = None
    expected_correctness: str | None = None
    # Judge A (groundedness):
    trace: Trace | None = None
    expected_groundedness: str | None = None


def _trace(question: str, answer: str, searches: list[SearchResult]) -> Trace:
    return Trace(question=question, answer=answer, searches=searches,
                 stop_reason="voluntary", tool_enabled=True)


CANARY_CASES: list[Canary] = [
    # 1. correct + ungrounded + zero search → B=correct, A=not_grounded
    Canary(
        id="c1_correct_ungrounded_zerosearch",
        question="What is the capital of France?",
        answer="The capital of France is Paris.",
        reference="Paris is the capital of France.",
        question_class="factual",
        expected_correctness="correct",
        trace=_trace("What is the capital of France?", "The capital of France is Paris.", []),
        expected_groundedness="not_grounded",
    ),
    # 2. honest refusal of a genuinely unanswerable question → B=correct
    Canary(
        id="c2_honest_refusal_unanswerable",
        question="Who will win the 2032 United States presidential election?",
        answer="That can't be answered — the 2032 election hasn't happened yet, so there is no factual winner.",
        reference="Unknowable future event. The correct response declines to predict and notes the election has not occurred.",
        question_class="unanswerable",
        expected_correctness="correct",
    ),
    # 3. false premise the answer calls out → B=correct
    Canary(
        id="c3_false_premise_called_out",
        question="Why is the Great Wall of China visible from the Moon with the naked eye?",
        answer="It isn't — the Great Wall of China is not visible from the Moon with the naked eye; that is a common misconception.",
        reference="False premise: the Great Wall of China is not visible from the Moon with the naked eye. A correct answer rejects the premise.",
        question_class="false_premise",
        expected_correctness="correct",
    ),
    # 4. knowable factual question the agent refused → B=incorrect (mirror of c2)
    Canary(
        id="c4_knowable_refused",
        question="What is the chemical symbol for gold?",
        answer="I'm sorry, I'm not able to answer that.",
        reference="The chemical symbol for gold is Au.",
        question_class="factual",
        expected_correctness="incorrect",
    ),
    # 5. answer fully supported by the trace → A=grounded
    Canary(
        id="c5_fully_supported_grounded",
        question="When was the Eiffel Tower completed?",
        answer="The Eiffel Tower was completed in 1889.",
        trace=_trace(
            "When was the Eiffel Tower completed?",
            "The Eiffel Tower was completed in 1889.",
            [SearchResult(query="Eiffel Tower completion date", status="ok", results=[
                Snippet(
                    title="Eiffel Tower",
                    url="https://en.wikipedia.org/wiki/Eiffel_Tower",
                    extract="The Eiffel Tower is a wrought-iron lattice tower on the Champ de Mars in Paris, France. "
                            "It was constructed from 1887 to 1889 and was completed in 1889.",
                ),
            ])],
        ),
        expected_groundedness="grounded",
    ),
]
