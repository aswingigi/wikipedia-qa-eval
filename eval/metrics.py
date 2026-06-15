"""Metric computation — pure functions over per-case results (no API). The judges emit 3-way labels;
for the 2x2 passes we collapse partially_* into the negative pole (partially_grounded -> not_grounded,
partially_correct -> incorrect). The raw labels are kept on each CaseResult for the per-case file.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from agents.agent import Trace
from eval.cases import Case


@dataclass
class CaseResult:
    case: Case
    open_answer: str
    closed_answer: str
    open_trace: Trace
    closed_trace: Trace
    correctness_open: str      # raw 3-way
    correctness_closed: str    # raw 3-way
    groundedness: str          # raw 3-way (open run)
    unsupported_claims: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def necessity(self) -> str:
        return necessity_bucket(is_correct(self.correctness_open), is_correct(self.correctness_closed))


def is_correct(label: str) -> bool:
    return label == "correct"


def is_grounded(label: str) -> bool:
    return label == "grounded"


def necessity_bucket(open_ok: bool, closed_ok: bool) -> str:
    if open_ok and not closed_ok:
        return "rescued"
    if not open_ok and closed_ok:
        return "hurt"
    if open_ok and closed_ok:
        return "ceremony"
    return "both_wrong"


def retrieved_chars(trace: Trace) -> int:
    return sum(len(snip.extract) for s in trace.searches for snip in s.results)


def aggregate(results: list[CaseResult]) -> dict:
    ok = [r for r in results if r.error is None]
    errored = [r for r in results if r.error is not None]

    nec = Counter(r.necessity for r in ok)
    necessity = {k: nec.get(k, 0) for k in ("rescued", "hurt", "ceremony", "both_wrong")}

    n = len(ok)
    correct_open = sum(1 for r in ok if is_correct(r.correctness_open))

    # groundedness 2x2: population = open answers that are correct AND needs_verification.
    population = [r for r in ok if is_correct(r.correctness_open) and r.case.needs_verification]
    g22 = {"grounded+rescued": 0, "grounded+ceremony": 0,
           "not_grounded+rescued": 0, "not_grounded+ceremony": 0}
    contradictory = []
    for r in population:
        row = "grounded" if is_grounded(r.groundedness) else "not_grounded"
        col = r.necessity  # open is correct => rescued or ceremony
        key = f"{row}+{col}"
        if key in g22:
            g22[key] += 1
        if row == "not_grounded" and col == "rescued":
            contradictory.append(r.case.id)

    unnecessary = [r.case.id for r in ok if not r.case.needs_verification and r.open_trace.search_count > 0]
    unguarded = [r.case.id for r in ok if r.case.needs_verification and r.open_trace.search_count == 0]

    def obs(traces: list[Trace]) -> dict:
        searches = [t.search_count for t in traces]
        chars = [retrieved_chars(t) for t in traces]
        denom = len(traces) or 1
        return {
            "total_searches": sum(searches), "mean_searches": sum(searches) / denom,
            "total_chars": sum(chars), "mean_chars": sum(chars) / denom,
        }

    return {
        "n": n,
        "errored": [r.case.id for r in errored],
        "necessity": necessity,
        "correctness_open": {"correct": correct_open, "n": n, "rate": (correct_open / n if n else 0.0)},
        "groundedness_population": len(population),
        "groundedness_2x2": g22,
        "contradictory_not_grounded_rescued": contradictory,
        "search_audit": {"unnecessary_retrieval": unnecessary, "unguarded": unguarded},
        "observability": {"open": obs([r.open_trace for r in ok]), "closed": obs([r.closed_trace for r in ok])},
        "category_coverage": dict(Counter(r.case.category for r in ok)),
    }
