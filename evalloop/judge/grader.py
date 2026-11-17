"""Judge grader: single-criterion, named categories, reasoning-first (T33).

Corpus section F, the calibration stack, prescribes a specific judge design:

- **F6: Binary criteria, one call per criterion** (F:170).  A single question with a
  yes/no answer, not a 1–5 scale, because "judges are most accurate on binary decisions".
- **F7: One call per criterion** (F:189).  Packing multiple criteria into one prompt
  compresses the scale and judges the wrong dimension.  Each criterion is its own call.
- **Reasoning-first** (F:220).  The judge writes its reasoning BEFORE its verdict, so the
  verdict follows from the reasoning rather than the other way around.

The judge prompt
----------------
The prompt is a system message that names the criterion, defines the two categories
(pass/fail or the caller's labels), and instructs the judge to reason first.  The user
message carries the artifact to judge.  The assistant response is parsed for a verdict
and the reasoning that preceded it.

No model call happens here.  This module builds the prompt and parses the response;
the caller (or a test) routes the call through ``capability/router.py``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

__all__ = [
    "Criterion",
    "JudgeConfig",
    "JudgeRequest",
    "JudgeVerdict",
    "build_judge_prompt",
    "parse_judge_response",
]


@dataclass(frozen=True, slots=True)
class Criterion:
    """One binary criterion the judge evaluates.

    ``name`` is a machine-readable id (e.g. ``"factual_accuracy"``).
    ``question`` is the human-readable question (e.g. ``"Is the answer factually accurate?"``).
    ``pass_label`` and ``fail_label`` are the two categories the judge must choose between.
    """

    name: str
    question: str
    pass_label: str = "PASS"
    fail_label: str = "FAIL"
    description: str = ""
    few_shot: tuple[tuple[str, str], ...] = ()  # (artifact, expected_verdict) pairs


@dataclass(frozen=True, slots=True)
class JudgeConfig:
    """Configuration for a judge: which criteria, and the prompt template."""

    criteria: tuple[Criterion, ...]
    system_preamble: str = (
        "You are an expert evaluator. For each criterion, you must FIRST write your reasoning, "
        "then on a new line give your verdict. Your reasoning must come before your verdict."
    )

    def __post_init__(self) -> None:
        if not self.criteria:
            raise ValueError("a judge must have at least one criterion")
        names = [c.name for c in self.criteria]
        if len(names) != len(set(names)):
            raise ValueError(f"criterion names must be unique, got duplicates in {names}")


@dataclass(frozen=True, slots=True)
class JudgeRequest:
    """What goes to the model: the system prompt and the user message, for one criterion."""

    criterion: Criterion
    system: str
    user: str
    artifact: str


@dataclass(frozen=True, slots=True)
class JudgeVerdict:
    """What comes back: the verdict, the reasoning, and whether the response was parseable."""

    criterion_name: str
    verdict: str  # pass_label or fail_label
    passed: bool
    reasoning: str
    raw_response: str
    parsed: bool  # True if the verdict was extracted; False if it had to be inferred


def build_judge_prompt(
    criterion: Criterion,
    artifact: str,
    *,
    preamble: str = "",
) -> JudgeRequest:
    """Build the system + user messages for one criterion on one artifact.

    The system message names the criterion, defines the two verdicts, and instructs
    reasoning-first.  The user message is the artifact to judge.  Few-shot examples
    from the criterion are included if present.
    """
    system_parts: list[str] = []
    if preamble:
        system_parts.append(preamble)
    system_parts.append(
        f"## Criterion: {criterion.name}\n\n"
        f"{criterion.question}\n\n"
        f"You must respond with EXACTLY one of these two verdicts:\n"
        f"- **{criterion.pass_label}** if the criterion is met\n"
        f"- **{criterion.fail_label}** if the criterion is not met\n\n"
        f"Write your reasoning FIRST, then on its own line write your verdict "
        f"as: VERDICT: {criterion.pass_label} or VERDICT: {criterion.fail_label}"
    )
    if criterion.description:
        system_parts.append(f"\n{criterion.description}")
    if criterion.few_shot:
        system_parts.append("\n## Examples")
        for i, (example_artifact, expected) in enumerate(criterion.few_shot, 1):
            system_parts.append(
                f"\nExample {i}:\nArtifact: {example_artifact}\nExpected verdict: {expected}"
            )
    system = "\n\n".join(system_parts)
    user = f"Please evaluate the following artifact:\n\n{artifact}"
    return JudgeRequest(criterion=criterion, system=system, user=user, artifact=artifact)


# Parse the verdict from the judge's response.
_VERDICT_RE = re.compile(r"VERDICT:\s*(\S+)", re.IGNORECASE)


def parse_judge_response(
    response: str,
    criterion: Criterion,
) -> JudgeVerdict:
    """Extract the verdict and reasoning from the judge's response.

    Looks for ``VERDICT: <label>`` in the response.  If found, everything before
    it is the reasoning.  If not found, infers from the presence of the pass/fail
    labels in the last line.
    """
    match = _VERDICT_RE.search(response)
    if match:
        raw_verdict = match.group(1).strip().rstrip(".,;:!?")
        # Everything before the VERDICT line is reasoning.
        reasoning = response[:match.start()].strip()
        passed = _matches_label(raw_verdict, criterion.pass_label)
        failed = _matches_label(raw_verdict, criterion.fail_label)
        if passed:
            return JudgeVerdict(
                criterion_name=criterion.name,
                verdict=criterion.pass_label,
                passed=True,
                reasoning=reasoning,
                raw_response=response,
                parsed=True,
            )
        if failed:
            return JudgeVerdict(
                criterion_name=criterion.name,
                verdict=criterion.fail_label,
                passed=False,
                reasoning=reasoning,
                raw_response=response,
                parsed=True,
            )
    # Fallback: check the last non-empty line for labels.
    lines = [line.strip() for line in response.strip().splitlines() if line.strip()]
    if lines:
        last = lines[-1]
        reasoning = "\n".join(lines[:-1]).strip()
        if criterion.pass_label.upper() in last.upper():
            return JudgeVerdict(criterion.name, criterion.pass_label, True, reasoning, response, parsed=False)
        if criterion.fail_label.upper() in last.upper():
            return JudgeVerdict(criterion.name, criterion.fail_label, False, reasoning, response, parsed=False)
    # Completely unparseable: default to fail (conservative).
    return JudgeVerdict(
        criterion_name=criterion.name,
        verdict=criterion.fail_label,
        passed=False,
        reasoning=response.strip(),
        raw_response=response,
        parsed=False,
    )


def _matches_label(text: str, label: str) -> bool:
    return text.upper() == label.upper()
