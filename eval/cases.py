"""Eval cases — I DRAFT (references live-verified 2026-06-15 against en.wikipedia.org), you verify/edit
before submission.

Authored FOR retrieval_necessity (not difficulty): name collisions/disambiguation, disputed/precise
numerics, and — weighted heaviest — facts genuinely not in memory (post worker-cutoff recent events),
plus answer-from-memory cases.

  - question_class ∈ {numeric, disambiguation, factual, false_premise, unanswerable} — the ONLY
    classes the judges branch on. It IS exposed to Judge B (run.py -> judges.run_judge_b renders
    "Question class: <...>"). The real cases use factual/numeric/disambiguation; false_premise and
    unanswerable are exercised by the canaries.
  - category is an authoring/coverage tag the judges never see (recent_event, name_collision,
    disputed_numeric, well_known): it records why the case exists.
  - memory_ok / needs_verification drive the search audit and the groundedness population.

Note: the Nile's length is genuinely disputed; the reference reflects Wikipedia's current figure
(7,088 km), which is the ground truth Judge B scores against here.
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


EVAL_CASES: list[Case] = [
    # ---- recent events (post worker-cutoff; needs_verification=True) ----
    Case(
        id="re_winter_olympics_2026",
        question="Which Italian cities were the main hosts of the 2026 Winter Olympics, and when were the Games held?",
        question_class="factual",
        reference="The 2026 Winter Olympics (Milano Cortina 2026) were co-hosted by Milan and Cortina d'Ampezzo, Italy, held 6–22 February 2026.",
        memory_ok=False, needs_verification=True, category="recent_event",
    ),
    Case(
        id="re_nobel_literature_2025",
        question="Who won the 2025 Nobel Prize in Literature?",
        question_class="factual",
        reference="The Hungarian novelist László Krasznahorkai won the 2025 Nobel Prize in Literature.",
        memory_ok=False, needs_verification=True, category="recent_event",
    ),
    Case(
        id="re_nobel_peace_2025",
        question="Who was awarded the 2025 Nobel Peace Prize?",
        question_class="factual",
        reference="María Corina Machado of Venezuela was awarded the 2025 Nobel Peace Prize.",
        memory_ok=False, needs_verification=True, category="recent_event",
    ),
    Case(
        id="re_super_bowl_lx",
        question="Which team won Super Bowl LX, and which team did they defeat?",
        question_class="factual",
        reference="The Seattle Seahawks won Super Bowl LX, defeating the New England Patriots 29–13.",
        memory_ok=False, needs_verification=True, category="recent_event",
    ),
    Case(
        id="re_ucl_final_2025",
        question="Which club won the 2025 UEFA Champions League final, and what was the score?",
        question_class="factual",
        reference="Paris Saint-Germain won the 2025 UEFA Champions League final, beating Inter Milan 5–0 in Munich on 31 May 2025.",
        memory_ok=False, needs_verification=True, category="recent_event",
    ),
    Case(
        id="re_ucl_final_2026",
        question="Who won the 2026 UEFA Champions League final, and how?",
        question_class="factual",
        reference="Paris Saint-Germain won the 2026 UEFA Champions League final, defeating Arsenal 4–3 on penalties after a 1–1 draw (after extra time) at the Puskás Aréna, Budapest, on 30 May 2026.",
        memory_ok=False, needs_verification=True, category="recent_event",
    ),
    Case(
        id="re_wimbledon_2025_mens",
        question="Who won the men's singles title at the 2025 Wimbledon Championships?",
        question_class="factual",
        reference="Jannik Sinner won the 2025 Wimbledon men's singles title, defeating Carlos Alcaraz in the final.",
        memory_ok=False, needs_verification=True, category="recent_event",
    ),
    Case(
        id="re_oscars_98_host",
        question="Who hosted the 98th Academy Awards, held in March 2026?",
        question_class="factual",
        reference="Conan O'Brien hosted the 98th Academy Awards (March 15, 2026), his second consecutive year as host.",
        memory_ok=False, needs_verification=True, category="recent_event",
    ),

    # ---- disambiguation / name collisions ----
    Case(
        id="dis_michael_i_jordan",
        question="The scientist Michael I. Jordan is a professor at which university, and what field is he best known for?",
        question_class="disambiguation",
        reference="Michael I. Jordan is a professor at the University of California, Berkeley, and is a leading researcher in machine learning, statistics, and artificial intelligence (not the basketball player).",
        memory_ok=False, needs_verification=True, category="name_collision",
    ),
    Case(
        id="dis_mercury_element",
        question="In chemistry, what are the chemical symbol and atomic number of the element mercury?",
        question_class="disambiguation",
        reference="The element mercury has the chemical symbol Hg and atomic number 80 (distinct from the planet Mercury or the Roman deity).",
        memory_ok=True, needs_verification=False, category="name_collision",
    ),
    Case(
        id="dis_georgia_capital",
        question="What is the capital of the country Georgia (not the U.S. state)?",
        question_class="disambiguation",
        reference="Tbilisi is the capital of the country Georgia (the U.S. state's capital is Atlanta).",
        memory_ok=True, needs_verification=False, category="name_collision",
    ),

    # ---- disputed / precise numerics ----
    Case(
        id="num_everest_height",
        question="What is the height of Mount Everest in meters, according to the most recent official survey?",
        question_class="numeric",
        reference="8,848.86 m (29,031 ft 8.5 in), per the 2020 joint China–Nepal survey.",
        memory_ok=False, needs_verification=True, category="disputed_numeric",
    ),
    Case(
        id="num_nile_length",
        question="How long is the Nile River, in kilometers?",
        question_class="numeric",
        reference="Approximately 7,088 km (4,404 mi); Wikipedia lists the Nile as the longest river in the world. The length is disputed — some sources cite about 6,650 km.",
        memory_ok=False, needs_verification=True, category="disputed_numeric",
    ),

    # ---- answer-from-memory (well known) ----
    Case(
        id="mem_meters_in_km",
        question="How many meters are in a kilometer?",
        question_class="numeric",
        reference="1,000 meters.",
        memory_ok=True, needs_verification=False, category="well_known",
    ),
    Case(
        id="mem_us_capital",
        question="What is the capital of the United States?",
        question_class="factual",
        reference="Washington, D.C.",
        memory_ok=True, needs_verification=False, category="well_known",
    ),
    Case(
        id="mem_oxygen_symbol",
        question="What is the chemical symbol for oxygen?",
        question_class="factual",
        reference="O.",
        memory_ok=True, needs_verification=False, category="well_known",
    ),
    Case(
        id="mem_largest_planet",
        question="What is the largest planet in the Solar System?",
        question_class="factual",
        reference="Jupiter.",
        memory_ok=True, needs_verification=False, category="well_known",
    ),
    Case(
        id="mem_moon_distance",
        question="What is the average distance from the Earth to the Moon, in kilometers?",
        question_class="numeric",
        reference="About 384,400 km (the Moon's average distance is roughly 384,399 km).",
        memory_ok=True, needs_verification=False, category="well_known",
    ),
]
