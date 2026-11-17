"""Calibration set, Cohen's kappa, and the runtime gate (T36).

Corpus F1 and F2:

- F1: "Validate against 150–200 human gold labels before use."  At least 50 fail cases.
- F2: "Cohen's κ = (p_o − p_e) / (1 − p_e)."  κ ≥ 0.6 to use, ≥ 0.8 to gate.

The runtime gate
----------------
The gate reads thresholds from the registry's ``rule_of_thumb``, not ``requires``:
- κ ≥ 0.6 — the judge may be used for evaluation.
- κ ≥ 0.8 — the judge may gate a release (block it on a failure).
- Flip rate > 10–15% — the judge is unreliable on this comparison (F4).

Cohen's κ
----------
Computed exactly as the corpus states: ``(p_o - p_e) / (1 - p_e)``, where ``p_o``
is observed agreement and ``p_e`` is chance agreement from the marginals.  When
``p_e == 1`` (perfect chance agreement), κ is defined as 1.0 when observers agree
perfectly, and 0.0 otherwise.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

__all__ = [
    "CalibrationReport",
    "CalibrationSet",
    "ConfusionMatrix",
    "GoldLabel",
    "KappaResult",
    "RuntimeGate",
    "cohens_kappa",
    "confusion_matrix",
]


@dataclass(frozen=True, slots=True)
class GoldLabel:
    """One human-labelled item in the calibration set."""

    item_id: str
    human_label: str  # the gold-standard label
    judge_label: str  # the judge's label for the same item


@dataclass(frozen=True, slots=True)
class ConfusionMatrix:
    """A 2x2 confusion matrix for binary classification."""

    true_positive: int  # human=pass, judge=pass
    false_positive: int  # human=fail, judge=pass
    false_negative: int  # human=pass, judge=fail
    true_negative: int  # human=fail, judge=fail

    @property
    def n(self) -> int:
        return self.true_positive + self.false_positive + self.false_negative + self.true_negative

    @property
    def accuracy(self) -> float:
        return (self.true_positive + self.true_negative) / self.n if self.n > 0 else 0.0

    @property
    def precision(self) -> float:
        """Precision on the pass class."""
        denom = self.true_positive + self.false_positive
        return self.true_positive / denom if denom > 0 else 0.0

    @property
    def recall(self) -> float:
        """Recall on the pass class."""
        denom = self.true_positive + self.false_negative
        return self.true_positive / denom if denom > 0 else 0.0

    @property
    def fail_recall(self) -> float:
        """Recall on the fail class (how many real failures the judge catches)."""
        denom = self.false_positive + self.true_negative
        return self.true_negative / denom if denom > 0 else 0.0

    @property
    def fail_precision(self) -> float:
        """Precision on the fail class."""
        denom = self.false_negative + self.true_negative
        return self.true_negative / denom if denom > 0 else 0.0


def confusion_matrix(
    labels: Sequence[GoldLabel],
    *,
    pass_label: str = "PASS",
) -> ConfusionMatrix:
    """Build a 2x2 confusion matrix from gold labels vs judge labels."""
    tp = fp = fn = tn = 0
    for label in labels:
        human_pass = label.human_label.upper() == pass_label.upper()
        judge_pass = label.judge_label.upper() == pass_label.upper()
        if human_pass and judge_pass:
            tp += 1
        elif not human_pass and judge_pass:
            fp += 1
        elif human_pass and not judge_pass:
            fn += 1
        else:
            tn += 1
    return ConfusionMatrix(tp, fp, fn, tn)


@dataclass(frozen=True, slots=True)
class KappaResult:
    """Cohen's κ, with the components that produced it."""

    kappa: float
    p_observed: float
    p_expected: float
    n: int
    interpretation: str  # "poor", "moderate", "substantial", "near-perfect"


def cohens_kappa(labels: Sequence[GoldLabel]) -> KappaResult:
    """Cohen's κ = (p_o − p_e) / (1 − p_e) (F2, F:62).

    Both raters label every item with one of two labels.  ``human_label`` is rater 1,
    ``judge_label`` is rater 2.
    """
    n = len(labels)
    if n == 0:
        return KappaResult(kappa=0.0, p_observed=0.0, p_expected=0.0, n=0, interpretation="poor")
    # Collect the label vocabulary from both raters.
    all_labels = sorted({l.human_label for l in labels} | {l.judge_label for l in labels})
    # Count agreements.
    agree = sum(1 for l in labels if l.human_label == l.judge_label)
    p_o = agree / n
    # Chance agreement from marginals.
    p_e = 0.0
    for label_value in all_labels:
        human_count = sum(1 for l in labels if l.human_label == label_value)
        judge_count = sum(1 for l in labels if l.judge_label == label_value)
        p_e += (human_count / n) * (judge_count / n)
    if p_e >= 1.0:
        kappa = 1.0 if p_o >= 1.0 else 0.0
    else:
        kappa = (p_o - p_e) / (1.0 - p_e)
    # F:72 bands.
    if kappa >= 0.8:
        interp = "near-perfect"
    elif kappa >= 0.6:
        interp = "substantial"
    elif kappa >= 0.4:
        interp = "moderate"
    else:
        interp = "poor"
    return KappaResult(kappa=kappa, p_observed=p_o, p_expected=p_e, n=n, interpretation=interp)


@dataclass(frozen=True, slots=True)
class CalibrationSet:
    """A set of gold-labelled items for calibrating the judge."""

    labels: tuple[GoldLabel, ...]
    pass_label: str = "PASS"
    fail_label: str = "FAIL"

    @property
    def n(self) -> int:
        return len(self.labels)

    @property
    def n_fail(self) -> int:
        return sum(1 for l in self.labels if l.human_label.upper() != self.pass_label.upper())

    @property
    def n_pass(self) -> int:
        return sum(1 for l in self.labels if l.human_label.upper() == self.pass_label.upper())


@dataclass(frozen=True, slots=True)
class RuntimeGate:
    """The result of checking whether the judge meets the calibration thresholds."""

    may_use: bool  # κ ≥ 0.6
    may_gate: bool  # κ ≥ 0.8
    kappa: KappaResult
    matrix: ConfusionMatrix
    flip_rate: float | None  # from position-swap, if available
    flip_rate_ok: bool  # True if flip_rate <= 15% or not measured
    reason: str


#: F:72: κ bands from the corpus.
_KAPPA_USE_THRESHOLD = 0.6
_KAPPA_GATE_THRESHOLD = 0.8
_FLIP_RATE_THRESHOLD = 0.15
_MIN_ITEMS = 150
_MIN_FAIL_CASES = 50


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    """Full calibration report: kappa, confusion matrix, gate decision, and diagnostics."""

    calibration_set: CalibrationSet
    kappa: KappaResult
    matrix: ConfusionMatrix
    gate: RuntimeGate
    warnings: tuple[str, ...]


def calibrate(
    cal_set: CalibrationSet,
    *,
    flip_rate: float | None = None,
) -> CalibrationReport:
    """Run the full calibration: kappa, confusion matrix, and runtime gate decision."""
    warnings: list[str] = []
    if cal_set.n < _MIN_ITEMS:
        warnings.append(
            f"calibration set has {cal_set.n} items; F1 recommends 150–200 (F:27)"
        )
    if cal_set.n_fail < _MIN_FAIL_CASES:
        warnings.append(
            f"calibration set has {cal_set.n_fail} fail cases; F1 recommends at least 50 (F:36)"
        )
    kappa = cohens_kappa(cal_set.labels)
    matrix = confusion_matrix(cal_set.labels, pass_label=cal_set.pass_label)
    may_use = kappa.kappa >= _KAPPA_USE_THRESHOLD
    may_gate = kappa.kappa >= _KAPPA_GATE_THRESHOLD
    flip_ok = flip_rate is None or flip_rate <= _FLIP_RATE_THRESHOLD
    if not flip_ok:
        warnings.append(
            f"position-swap flip rate {flip_rate:.1%} exceeds {_FLIP_RATE_THRESHOLD:.0%} (F:140)"
        )
    reason_parts: list[str] = []
    if may_gate:
        reason_parts.append(f"κ = {kappa.kappa:.2f} ({kappa.interpretation}): may use and may gate releases")
    elif may_use:
        reason_parts.append(f"κ = {kappa.kappa:.2f} ({kappa.interpretation}): may use but not gate releases")
    else:
        reason_parts.append(f"κ = {kappa.kappa:.2f} ({kappa.interpretation}): do not use this judge")
    reason_parts.append(
        f"accuracy {matrix.accuracy:.1%}, fail recall {matrix.fail_recall:.1%}"
    )
    gate = RuntimeGate(
        may_use=may_use,
        may_gate=may_gate,
        kappa=kappa,
        matrix=matrix,
        flip_rate=flip_rate,
        flip_rate_ok=flip_ok,
        reason="; ".join(reason_parts),
    )
    return CalibrationReport(
        calibration_set=cal_set,
        kappa=kappa,
        matrix=matrix,
        gate=gate,
        warnings=tuple(warnings),
    )
