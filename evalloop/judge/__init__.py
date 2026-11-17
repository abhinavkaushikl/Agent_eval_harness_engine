"""The judge grader: LLM-as-a-judge with calibration, bias control, and trust gating (M4).

This package implements T33–T36:

- **T33** Judge grader: single-criterion, named categories, reasoning-first.
- **T34** Cross-family hard assertion (enforced in ``capability/router.py``).
- **T35** Position swap + flip-rate tracking.
- **T36** Calibration set + Cohen's kappa + runtime gate.

The corpus section F is the authority.  The judge grader is rung 4 of the
grading ladder (A:95), above deterministic (3) and below human (5).
"""

from __future__ import annotations

from evalloop.judge.grader import (
    Criterion,
    JudgeConfig,
    JudgeRequest,
    JudgeVerdict,
    build_judge_prompt,
    parse_judge_response,
)
from evalloop.judge.position_swap import (
    PositionPair,
    SwapResult,
    SwapSummary,
    check_position_bias,
)
from evalloop.judge.calibration import (
    CalibrationReport,
    CalibrationSet,
    GoldLabel,
    KappaResult,
    RuntimeGate,
    cohens_kappa,
    confusion_matrix,
)

__all__ = [
    "CalibrationReport",
    "CalibrationSet",
    "Criterion",
    "GoldLabel",
    "JudgeConfig",
    "JudgeRequest",
    "JudgeVerdict",
    "KappaResult",
    "PositionPair",
    "RuntimeGate",
    "SwapResult",
    "SwapSummary",
    "build_judge_prompt",
    "check_position_bias",
    "cohens_kappa",
    "confusion_matrix",
    "parse_judge_response",
]
