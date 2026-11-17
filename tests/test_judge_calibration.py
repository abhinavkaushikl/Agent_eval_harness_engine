"""Tests for evalloop.judge.calibration (T36)."""

from __future__ import annotations

from evalloop.judge.calibration import (
    CalibrationReport,
    CalibrationSet,
    ConfusionMatrix,
    GoldLabel,
    KappaResult,
    RuntimeGate,
    calibrate,
    cohens_kappa,
    confusion_matrix,
)

import pytest


# ---------------------------------------------------------------------------
# ConfusionMatrix
# ---------------------------------------------------------------------------

def test_confusion_matrix_basic() -> None:
    labels = [
        GoldLabel("1", "PASS", "PASS"),
        GoldLabel("2", "PASS", "FAIL"),
        GoldLabel("3", "FAIL", "PASS"),
        GoldLabel("4", "FAIL", "FAIL"),
    ]
    cm = confusion_matrix(labels)
    assert cm.true_positive == 1
    assert cm.false_negative == 1
    assert cm.false_positive == 1
    assert cm.true_negative == 1
    assert cm.n == 4
    assert cm.accuracy == 0.5


def test_confusion_matrix_perfect() -> None:
    labels = [
        GoldLabel("1", "PASS", "PASS"),
        GoldLabel("2", "FAIL", "FAIL"),
    ]
    cm = confusion_matrix(labels)
    assert cm.accuracy == 1.0
    assert cm.precision == 1.0
    assert cm.recall == 1.0
    assert cm.fail_recall == 1.0
    assert cm.fail_precision == 1.0


def test_confusion_matrix_all_pass() -> None:
    labels = [GoldLabel(str(i), "PASS", "PASS") for i in range(5)]
    cm = confusion_matrix(labels)
    assert cm.true_positive == 5
    assert cm.true_negative == 0
    assert cm.precision == 1.0
    assert cm.recall == 1.0
    assert cm.fail_recall == 0.0  # no fail items


def test_confusion_matrix_custom_pass_label() -> None:
    labels = [
        GoldLabel("1", "FAITHFUL", "FAITHFUL"),
        GoldLabel("2", "UNFAITHFUL", "FAITHFUL"),
    ]
    cm = confusion_matrix(labels, pass_label="FAITHFUL")
    assert cm.true_positive == 1
    assert cm.false_positive == 1


# ---------------------------------------------------------------------------
# Cohen's kappa
# ---------------------------------------------------------------------------

def test_kappa_perfect_agreement() -> None:
    labels = [
        GoldLabel("1", "PASS", "PASS"),
        GoldLabel("2", "FAIL", "FAIL"),
        GoldLabel("3", "PASS", "PASS"),
        GoldLabel("4", "FAIL", "FAIL"),
    ]
    k = cohens_kappa(labels)
    assert k.kappa == 1.0
    assert k.p_observed == 1.0
    assert k.interpretation == "near-perfect"


def test_kappa_no_agreement() -> None:
    labels = [
        GoldLabel("1", "PASS", "FAIL"),
        GoldLabel("2", "FAIL", "PASS"),
        GoldLabel("3", "PASS", "FAIL"),
        GoldLabel("4", "FAIL", "PASS"),
    ]
    k = cohens_kappa(labels)
    assert k.kappa < 0  # worse than chance
    assert k.p_observed == 0.0
    assert k.interpretation == "poor"


def test_kappa_empty() -> None:
    k = cohens_kappa([])
    assert k.kappa == 0.0
    assert k.n == 0
    assert k.interpretation == "poor"


def test_kappa_moderate() -> None:
    # 8 out of 10 agree with 50/50 base rate -> p_o=0.8, p_e=0.5, kappa=0.6
    # That's right at the substantial boundary, so use a split that lands clearly moderate.
    # 15 out of 20 agree: p_o=0.75; human 10P/10F, judge 10P/10F -> p_e=0.5
    # kappa = (0.75-0.5)/(1-0.5) = 0.5 — moderate
    labels: list[GoldLabel] = []
    # 8 agree-pass
    labels.extend(GoldLabel(str(i), "PASS", "PASS") for i in range(8))
    # 2 disagree (human PASS, judge FAIL)
    labels.extend(GoldLabel(str(8 + i), "PASS", "FAIL") for i in range(2))
    # 7 agree-fail
    labels.extend(GoldLabel(str(10 + i), "FAIL", "FAIL") for i in range(7))
    # 3 disagree (human FAIL, judge PASS)
    labels.extend(GoldLabel(str(17 + i), "FAIL", "PASS") for i in range(3))
    k = cohens_kappa(labels)
    assert k.n == 20
    assert 0.4 < k.kappa < 0.6
    assert k.interpretation == "moderate"


def test_kappa_all_same_label() -> None:
    # Both raters always say PASS: p_o = 1.0, p_e = 1.0
    labels = [GoldLabel(str(i), "PASS", "PASS") for i in range(10)]
    k = cohens_kappa(labels)
    # When p_e >= 1.0 and p_o >= 1.0, kappa is defined as 1.0
    assert k.kappa == 1.0


# ---------------------------------------------------------------------------
# CalibrationSet
# ---------------------------------------------------------------------------

def test_calibration_set_counts() -> None:
    labels = (
        GoldLabel("1", "PASS", "PASS"),
        GoldLabel("2", "FAIL", "FAIL"),
        GoldLabel("3", "FAIL", "PASS"),
    )
    cs = CalibrationSet(labels=labels)
    assert cs.n == 3
    assert cs.n_pass == 1
    assert cs.n_fail == 2


# ---------------------------------------------------------------------------
# calibrate (full pipeline)
# ---------------------------------------------------------------------------

def _make_labels(n_agree_pass: int, n_agree_fail: int, n_fp: int, n_fn: int) -> tuple[GoldLabel, ...]:
    idx = 0
    labels: list[GoldLabel] = []
    for _ in range(n_agree_pass):
        labels.append(GoldLabel(str(idx), "PASS", "PASS"))
        idx += 1
    for _ in range(n_agree_fail):
        labels.append(GoldLabel(str(idx), "FAIL", "FAIL"))
        idx += 1
    for _ in range(n_fp):
        labels.append(GoldLabel(str(idx), "FAIL", "PASS"))
        idx += 1
    for _ in range(n_fn):
        labels.append(GoldLabel(str(idx), "PASS", "FAIL"))
        idx += 1
    return tuple(labels)


def test_calibrate_good_judge() -> None:
    # 90 pass agree, 60 fail agree, 5 FP, 5 FN = 160 items, 50+ fails
    labels = _make_labels(90, 60, 5, 5)
    cs = CalibrationSet(labels=labels)
    report = calibrate(cs)
    assert report.gate.may_use is True
    assert report.kappa.kappa > 0.6
    assert report.matrix.n == 160
    assert len(report.warnings) == 0  # meets F1 thresholds


def test_calibrate_poor_judge() -> None:
    # 30 pass agree, 20 fail agree, 50 FP, 50 FN = very noisy
    labels = _make_labels(30, 20, 50, 50)
    cs = CalibrationSet(labels=labels)
    report = calibrate(cs)
    assert report.gate.may_use is False
    assert report.gate.may_gate is False
    assert report.kappa.interpretation == "poor"


def test_calibrate_too_few_items_warns() -> None:
    labels = _make_labels(5, 5, 1, 1)
    cs = CalibrationSet(labels=labels)
    report = calibrate(cs)
    assert any("150" in w for w in report.warnings)


def test_calibrate_too_few_fail_cases_warns() -> None:
    # 130 pass, 10 fail = enough items but not enough fails
    labels = _make_labels(130, 10, 5, 5)
    cs = CalibrationSet(labels=labels)
    report = calibrate(cs)
    assert any("50" in w for w in report.warnings)


def test_calibrate_flip_rate_warning() -> None:
    labels = _make_labels(90, 60, 5, 5)
    cs = CalibrationSet(labels=labels)
    report = calibrate(cs, flip_rate=0.25)
    assert any("flip rate" in w for w in report.warnings)
    assert report.gate.flip_rate_ok is False


def test_calibrate_flip_rate_ok() -> None:
    labels = _make_labels(90, 60, 5, 5)
    cs = CalibrationSet(labels=labels)
    report = calibrate(cs, flip_rate=0.05)
    assert report.gate.flip_rate_ok is True


def test_calibrate_gate_may_gate() -> None:
    # Very high agreement: kappa should be >= 0.8
    labels = _make_labels(95, 55, 2, 3)
    cs = CalibrationSet(labels=labels)
    report = calibrate(cs)
    assert report.gate.may_gate is True
    assert "may gate" in report.gate.reason


def test_calibrate_reason_includes_accuracy() -> None:
    labels = _make_labels(90, 60, 5, 5)
    cs = CalibrationSet(labels=labels)
    report = calibrate(cs)
    assert "accuracy" in report.gate.reason
