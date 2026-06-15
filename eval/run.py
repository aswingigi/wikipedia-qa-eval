"""Eval orchestrator: parallel canary gate + parallel full run, with report/per-case writers.

    python -m eval.run canaries [--judge-a-version v --judge-b-version v --concurrency N]
    python -m eval.run full [--prompt-version v --judge-a-version v --judge-b-version v --concurrency N]

Canaries run the real judges on synthetic inputs and STOP (pass -> await go-ahead; fail -> report
only, never editing prompts/labels). The full run scores every case open vs closed and writes two
artifacts under results/.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from agents.agent import SEARCH_WIKIPEDIA_TOOL, WORKER_MODEL, Trace, run_agent
from agents.prompts import DEFAULT_VERSION as DEFAULT_WORKER_VERSION
from agents.prompts import available_versions, get_prompt
from eval.canaries import CANARY_CASES
from eval.cases import EVAL_CASES
from eval.judge_prompts import (
    DEFAULT_JUDGE_A_VERSION,
    DEFAULT_JUDGE_B_VERSION,
    available_judge_a_versions,
    available_judge_b_versions,
    get_judge_a_prompt,
    get_judge_b_prompt,
)
from eval.judges import JUDGE_MODEL, run_judge_a, run_judge_b
from eval.metrics import CaseResult, aggregate, retrieved_chars

RESULTS_DIR = Path("results")
DEFAULT_CONCURRENCY = 2  # live MediaWiki API rate-limits (HTTP 429) under load; raise cautiously


def _client():
    import anthropic
    return anthropic.Anthropic()


def _empty_trace(question: str) -> Trace:
    return Trace(question=question, answer="", searches=[], stop_reason="voluntary", tool_enabled=False)


# ---- full run ----------------------------------------------------------------

def evaluate_case(case, *, client, open_prompt, closed_prompt, judge_a_prompt, judge_b_prompt) -> CaseResult:
    try:
        open_trace = run_agent(case.question, tools=[SEARCH_WIKIPEDIA_TOOL], system_prompt=open_prompt, client=client)
        closed_trace = run_agent(case.question, tools=[], system_prompt=closed_prompt, client=client)
        cb_open = run_judge_b(client, question=case.question, answer=open_trace.answer,
                              reference=case.reference, question_class=case.question_class, prompt=judge_b_prompt)
        cb_closed = run_judge_b(client, question=case.question, answer=closed_trace.answer,
                                reference=case.reference, question_class=case.question_class, prompt=judge_b_prompt)
        ja = run_judge_a(client, question=case.question, answer=open_trace.answer,
                         trace=open_trace, prompt=judge_a_prompt)
        return CaseResult(
            case=case, open_answer=open_trace.answer, closed_answer=closed_trace.answer,
            open_trace=open_trace, closed_trace=closed_trace,
            correctness_open=cb_open.correctness, correctness_closed=cb_closed.correctness,
            groundedness=ja.groundedness, unsupported_claims=ja.unsupported_claims,
            correctness_rationale_open=cb_open.correctness_rationale,
            correctness_rationale_closed=cb_closed.correctness_rationale,
            drift_note_open=cb_open.drift_note, drift_note_closed=cb_closed.drift_note,
            groundedness_rationale=ja.rationale,
        )
    except Exception as e:
        return CaseResult(
            case=case, open_answer="", closed_answer="",
            open_trace=_empty_trace(case.question), closed_trace=_empty_trace(case.question),
            correctness_open="incorrect", correctness_closed="incorrect", groundedness="not_grounded",
            error=f"{type(e).__name__}: {e}",
        )


def run_full(args) -> int:
    open_prompt = get_prompt(args.prompt_version, open_book=True)
    closed_prompt = get_prompt(args.prompt_version, open_book=False)
    judge_a_prompt = get_judge_a_prompt(args.judge_a_version)
    judge_b_prompt = get_judge_b_prompt(args.judge_b_version)
    missing = _empty_prompts({"worker open-book": open_prompt, "worker closed-book": closed_prompt,
                              "Judge A": judge_a_prompt, "Judge B": judge_b_prompt})
    if missing:
        print(f"error: empty prompt(s): {', '.join(missing)} — author them first.", file=sys.stderr)
        return 2
    if not EVAL_CASES:
        print("error: EVAL_CASES is empty — author cases in eval/cases.py.", file=sys.stderr)
        return 2

    client = _client()
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futures = [
            ex.submit(evaluate_case, c, client=client, open_prompt=open_prompt, closed_prompt=closed_prompt,
                      judge_a_prompt=judge_a_prompt, judge_b_prompt=judge_b_prompt)
            for c in EVAL_CASES
        ]
        results = [f.result() for f in futures]
    results.sort(key=lambda r: r.case.id)

    summary = aggregate(results)
    versions = {
        "worker_model": WORKER_MODEL, "worker": args.prompt_version, "judge_model": JUDGE_MODEL,
        "judge_a": args.judge_a_version, "judge_b": args.judge_b_version,
    }
    runid = datetime.now().strftime("%Y%m%d-%H%M%S")
    RESULTS_DIR.mkdir(exist_ok=True)
    report = _format_report(summary, versions, runid)
    report_path = RESULTS_DIR / f"{runid}-report.md"
    cases_path = RESULTS_DIR / f"{runid}-cases.json"
    report_path.write_text(report)
    cases_path.write_text(json.dumps([_case_to_dict(r) for r in results], indent=2, ensure_ascii=False))

    print(report)
    print(f"\nwrote {report_path}\nwrote {cases_path}")
    return 0


# ---- canary gate -------------------------------------------------------------

def canary_units(cases) -> list[tuple]:
    """Which judge(s) each canary exercises: (canary, 'A'|'B'). Pure — used by the no-API wiring test."""
    units = []
    for c in cases:
        if c.expected_correctness is not None:
            units.append((c, "B"))
        if c.expected_groundedness is not None:
            units.append((c, "A"))
    return units


def run_canaries(args) -> int:
    units = canary_units(CANARY_CASES)
    ja_prompt = get_judge_a_prompt(args.judge_a_version)
    jb_prompt = get_judge_b_prompt(args.judge_b_version)
    needed = {}
    if any(j == "A" for _, j in units):
        needed["Judge A"] = ja_prompt
    if any(j == "B" for _, j in units):
        needed["Judge B"] = jb_prompt
    missing = _empty_prompts(needed)
    if missing:
        print(f"error: empty judge prompt(s): {', '.join(missing)} — author them in eval/judge_prompts.py.",
              file=sys.stderr)
        return 2

    client = _client()

    def run_unit(unit):
        c, judge = unit
        try:
            if judge == "B":
                v = run_judge_b(client, question=c.question, answer=c.answer, reference=c.reference,
                                question_class=c.question_class, prompt=jb_prompt)
                return (c.id, "B(correctness)", c.expected_correctness, v.correctness)
            v = run_judge_a(client, question=c.question, answer=c.answer, trace=c.trace, prompt=ja_prompt)
            return (c.id, "A(groundedness)", c.expected_groundedness, v.groundedness)
        except Exception as e:
            label = "B(correctness)" if judge == "B" else "A(groundedness)"
            expected = c.expected_correctness if judge == "B" else c.expected_groundedness
            return (c.id, label, expected, f"ERROR: {type(e).__name__}: {e}")

    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        records = list(ex.map(run_unit, units))
    records.sort(key=lambda r: (r[0], r[1]))

    print("=== canary gate ===")
    passed = 0
    for cid, judge, expected, actual in records:
        ok = expected == actual
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {cid} {judge}: expected={expected} actual={actual}")
    print(f"\n{passed}/{len(records)} canary checks passed")

    if passed != len(records):
        print("Canary gate FAILED — not editing prompts or expected labels. Stopping.", file=sys.stderr)
        return 1
    print("Canary gate passed. Stopping before the first real run — awaiting your go-ahead.")
    return 0


# ---- helpers -----------------------------------------------------------------

def _empty_prompts(named: dict[str, str]) -> list[str]:
    return [name for name, text in named.items() if not (text or "").strip()]


def _trace_to_dict(t: Trace) -> dict:
    return {
        "search_count": t.search_count,
        "stop_reason": t.stop_reason,
        "searches": [
            {
                "query": s.query, "status": s.status, "error": s.error,
                "results": [{"title": x.title, "url": x.url, "extract": x.extract} for x in s.results],
            }
            for s in t.searches
        ],
    }


def _case_to_dict(r: CaseResult) -> dict:
    c = r.case
    return {
        "id": c.id, "question": c.question, "question_class": c.question_class, "category": c.category,
        "memory_ok": c.memory_ok, "needs_verification": c.needs_verification, "reference": c.reference,
        "open_answer": r.open_answer, "closed_answer": r.closed_answer,
        "correctness_open": r.correctness_open, "correctness_closed": r.correctness_closed,
        "correctness_rationale_open": r.correctness_rationale_open,
        "correctness_rationale_closed": r.correctness_rationale_closed,
        "drift_note_open": r.drift_note_open, "drift_note_closed": r.drift_note_closed,
        "groundedness": r.groundedness, "groundedness_rationale": r.groundedness_rationale,
        "unsupported_claims": r.unsupported_claims,
        "necessity": r.necessity, "open_trace": _trace_to_dict(r.open_trace), "error": r.error,
    }


def _format_report(s: dict, v: dict, runid: str) -> str:
    nec, g, obs, audit, co = (s["necessity"], s["groundedness_2x2"], s["observability"],
                              s["search_audit"], s["correctness_open"])
    L = [
        f"# Eval report — {runid}",
        "",
        f"- worker model: {v['worker_model']} | prompt version: {v['worker']}",
        f"- judge model: {v['judge_model']} | Judge A: {v['judge_a']} | Judge B: {v['judge_b']}",
        f"- cases scored: {s['n']}" + (f" | errored: {len(s['errored'])} {s['errored']}" if s['errored'] else ""),
        "",
        "> Single-sample run (one open + one closed + one judge call per case). Expect run-to-run "
        "variation; treat small differences as noise.",
        "",
        "## retrieval_necessity (2x2)",
        f"- rescued (retrieval needed): {nec['rescued']}",
        f"- hurt (retrieval degraded): {nec['hurt']}",
        f"- ceremony (correct both): {nec['ceremony']}",
        f"- both_wrong (agent failed): {nec['both_wrong']}",
        f"- sum {sum(nec.values())} = scored {s['n']}",
        "",
        "## correctness (open run)",
        f"- {co['correct']}/{co['n']} correct (rate {co['rate']:.0%})",
        "",
        "## groundedness (2x2; population = correct & needs_verification open answers)",
        f"- population: {s['groundedness_population']}",
        f"- grounded + rescued (ideal): {g['grounded+rescued']}",
        f"- grounded + ceremony (verification): {g['grounded+ceremony']}",
        f"- not_grounded + ceremony (theatrics): {g['not_grounded+ceremony']}",
        f"- not_grounded + rescued (contradictory): {g['not_grounded+rescued']} {s['contradictory_not_grounded_rescued']}",
        "",
        "## search audit (vs tags, open run)",
        f"- unnecessary_retrieval (searched on needs_verification=False): "
        f"{len(audit['unnecessary_retrieval'])} {audit['unnecessary_retrieval']}",
        f"- unguarded (skipped search on needs_verification=True): {len(audit['unguarded'])} {audit['unguarded']}",
        "",
        "## observability",
    ]
    for ver in ("open", "closed"):
        o = obs[ver]
        L.append(f"- {ver}: searches total {o['total_searches']} (mean {o['mean_searches']:.2f}); "
                 f"retrieved chars total {o['total_chars']} (mean {o['mean_chars']:.0f})")
    L += ["", "## category coverage"]
    for cat, count in sorted(s["category_coverage"].items()):
        L.append(f"- {cat}: {count}")
    return "\n".join(L) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(prog="eval.run")
    sub = parser.add_subparsers(dest="mode", required=True)
    for name in ("canaries", "full"):
        sp = sub.add_parser(name)
        sp.add_argument("--judge-a-version", default=DEFAULT_JUDGE_A_VERSION, choices=available_judge_a_versions())
        sp.add_argument("--judge-b-version", default=DEFAULT_JUDGE_B_VERSION, choices=available_judge_b_versions())
        sp.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
        if name == "full":
            sp.add_argument("--prompt-version", default=DEFAULT_WORKER_VERSION, choices=available_versions())
    args = parser.parse_args()

    load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: ANTHROPIC_API_KEY not set (put it in .env).", file=sys.stderr)
        return 2
    return run_canaries(args) if args.mode == "canaries" else run_full(args)


if __name__ == "__main__":
    sys.exit(main())
