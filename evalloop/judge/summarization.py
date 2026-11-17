"""Summarization situation: faithfulness + length companion (T37).

Gate 4 requirement: "Summarization judged end-to-end by a calibrated cross-family
judge, reusing M0–M3 components without architectural changes."

This module defines the two criteria for summarization evaluation:

1. **Faithfulness** — is the summary factually consistent with the source document?
   (Section G's ``G3_faithfulness``: "every claim in the summary must trace to a passage
   in the source.")

2. **Length companion** — is the summary the right length?  A judge that prefers longer
   summaries needs a length check as a companion (E3: length-controlled win rate).

Both are :class:`Criterion` instances that plug into the judge grader (T33).
The judge routes through the router (T34 cross-family enforcement), and the
calibration gate (T36) must pass before the judge's verdicts count.
"""

from __future__ import annotations

from dataclasses import dataclass

from evalloop.judge.grader import Criterion, JudgeConfig

__all__ = [
    "FAITHFULNESS_CRITERION",
    "LENGTH_CRITERION",
    "SummarizationConfig",
    "summarization_config",
    "check_length",
]


FAITHFULNESS_CRITERION = Criterion(
    name="faithfulness",
    question=(
        "Is every claim in the summary supported by the source document? "
        "A summary is faithful if it contains no information that cannot be traced "
        "to a specific passage in the source. Paraphrasing is acceptable; "
        "fabrication or inference beyond what the source states is not."
    ),
    pass_label="FAITHFUL",
    fail_label="UNFAITHFUL",
    description=(
        "Section G3 (G:98): 'Faithfulness means every claim in the summary traces to the source. "
        "A hallucinated detail, even a plausible one, is a faithfulness failure.'"
    ),
)


LENGTH_CRITERION = Criterion(
    name="length_appropriateness",
    question=(
        "Is the summary an appropriate length for the source document? "
        "A summary should be significantly shorter than the source while capturing "
        "the key information. An excessively long summary may score higher on "
        "content coverage but defeats the purpose of summarization."
    ),
    pass_label="APPROPRIATE",
    fail_label="INAPPROPRIATE",
    description=(
        "E3 companion: a length check prevents the judge from preferring longer "
        "summaries that contain more information at the cost of conciseness."
    ),
)


@dataclass(frozen=True, slots=True)
class SummarizationConfig:
    """Configuration for summarization evaluation: the two criteria and length bounds."""

    faithfulness: Criterion
    length: Criterion
    max_length_ratio: float  # summary / source length ratio above which length fails
    min_length_ratio: float  # summary / source length ratio below which length fails

    def judge_config(self) -> JudgeConfig:
        """A :class:`JudgeConfig` with both criteria, for the judge grader."""
        return JudgeConfig(criteria=(self.faithfulness, self.length))


def summarization_config(
    *,
    max_length_ratio: float = 0.5,
    min_length_ratio: float = 0.05,
) -> SummarizationConfig:
    """Build the default summarization evaluation config.

    ``max_length_ratio``: a summary longer than 50% of the source is too long.
    ``min_length_ratio``: a summary shorter than 5% of the source is too short.
    """
    return SummarizationConfig(
        faithfulness=FAITHFULNESS_CRITERION,
        length=LENGTH_CRITERION,
        max_length_ratio=max_length_ratio,
        min_length_ratio=min_length_ratio,
    )


@dataclass(frozen=True, slots=True)
class LengthCheck:
    """The result of a deterministic length check (companion to the judge's faithfulness verdict)."""

    source_length: int
    summary_length: int
    ratio: float
    passed: bool
    reason: str


def check_length(
    source: str,
    summary: str,
    *,
    max_ratio: float = 0.5,
    min_ratio: float = 0.05,
) -> LengthCheck:
    """Deterministic length companion: is the summary within the acceptable length range?

    This is NOT the judge's length criterion (which is an LLM call); this is the
    fast, deterministic check that runs alongside it.
    """
    source_len = len(source.split())
    summary_len = len(summary.split())
    if source_len == 0:
        return LengthCheck(0, summary_len, 0.0, True, "source is empty; no length check needed")
    ratio = summary_len / source_len
    if ratio > max_ratio:
        return LengthCheck(
            source_len, summary_len, ratio, False,
            f"summary is {ratio:.0%} of source length ({summary_len}/{source_len} words), "
            f"above the {max_ratio:.0%} maximum — too verbose for a summary"
        )
    if ratio < min_ratio:
        return LengthCheck(
            source_len, summary_len, ratio, False,
            f"summary is {ratio:.1%} of source length ({summary_len}/{source_len} words), "
            f"below the {min_ratio:.0%} minimum — too terse"
        )
    return LengthCheck(
        source_len, summary_len, ratio, True,
        f"summary is {ratio:.0%} of source length ({summary_len}/{source_len} words)"
    )
