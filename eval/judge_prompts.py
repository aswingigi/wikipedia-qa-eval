"""Judge system prompts — AUTHORED BY YOU, versioned per judge so you can iterate each independently.

Judge A scores groundedness (reference-blind). Judge B scores correctness (reference-aware, and
branches on question_class ∈ {numeric, disambiguation, factual, false_premise, unanswerable}). Both
registries ship empty; the harness errors if a selected version is empty. I never write/edit the
prompt text — only these placeholders and the getters.
"""
from __future__ import annotations

JUDGE_A_PROMPTS: dict[str, str] = {
    "baseline": "",  # TODO: you author — groundedness judge (reference-blind)
}
JUDGE_B_PROMPTS: dict[str, str] = {
    "baseline": "",  # TODO: you author — correctness judge (reference-aware; branch on question_class)
}

DEFAULT_JUDGE_A_VERSION = "baseline"
DEFAULT_JUDGE_B_VERSION = "baseline"


def available_judge_a_versions() -> list[str]:
    return list(JUDGE_A_PROMPTS)


def available_judge_b_versions() -> list[str]:
    return list(JUDGE_B_PROMPTS)


def get_judge_a_prompt(version: str = DEFAULT_JUDGE_A_VERSION) -> str:
    return _get(JUDGE_A_PROMPTS, version, "Judge A")


def get_judge_b_prompt(version: str = DEFAULT_JUDGE_B_VERSION) -> str:
    return _get(JUDGE_B_PROMPTS, version, "Judge B")


def _get(registry: dict[str, str], version: str, label: str) -> str:
    try:
        return registry[version]
    except KeyError:
        raise KeyError(f"unknown {label} prompt version {version!r}; available: {', '.join(registry)}")
