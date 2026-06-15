"""Eval cases — I DRAFT (references live-verified), you verify/edit before submission.

Authored FOR retrieval_necessity (not difficulty): name collisions/disambiguation, disputed/precise
numerics, and — weighted heaviest — facts genuinely not in memory (post worker-cutoff recent events),
plus answer-from-memory cases.

  - question_class ∈ {numeric, disambiguation, factual, false_premise, unanswerable} — the ONLY
    classes the judges branch on (Judge B sees it; Judge A does not).
  - category is an authoring/coverage tag the judges never see (recent_event, well_known,
    name_collision, disputed_numeric, ...): it records why the case exists.
  - memory_ok / needs_verification drive the search audit and the groundedness population.

EVAL_CASES is populated in build milestone 2 with ~18 live-verified cases.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Case:
    id: str
    question: str
    question_class: str  # numeric | disambiguation | factual | false_premise | unanswerable
    reference: str
    memory_ok: bool
    needs_verification: bool
    category: str  # coverage tag (judges never see this)


EVAL_CASES: list[Case] = []  # filled in milestone 2 (live-verified)
