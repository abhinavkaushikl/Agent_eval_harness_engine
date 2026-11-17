"""Tests for the diagnostics module (T30)."""

from __future__ import annotations

from evalloop.stats.diagnostics import (
    DiagnosticKind,
    diagnose_ceiling,
    diagnose_floor,
    diagnose_length_spike,
    diagnose_score_jump,
    run_all_diagnostics,
)


class TestScoreJump:
    def test_clean_improvement(self) -> None:
        result = diagnose_score_jump(regressions=2, improvements=20, total_items=100)
        assert not result.flagged
        assert result.kind == DiagnosticKind.score_jump

    def test_flags_too_many_flips(self) -> None:
        """E1: more than half the items flipped."""
        result = diagnose_score_jump(regressions=30, improvements=30, total_items=100)
        assert result.flagged
        assert "more than half" in result.explanation

    def test_flags_regressions_outnumber_improvements(self) -> None:
        result = diagnose_score_jump(regressions=15, improvements=5, total_items=100)
        assert result.flagged
        assert "regressions" in result.explanation

    def test_pure_degradation(self) -> None:
        result = diagnose_score_jump(regressions=10, improvements=0, total_items=100)
        assert result.flagged
        assert "degradation" in result.explanation

    def test_no_flips_is_clean(self) -> None:
        result = diagnose_score_jump(regressions=0, improvements=0, total_items=100)
        assert not result.flagged


class TestLengthSpike:
    def test_no_spike(self) -> None:
        result = diagnose_length_spike([100, 100, 100], [105, 105, 105])
        assert not result.flagged

    def test_flags_spike(self) -> None:
        """E3: length increase above threshold."""
        result = diagnose_length_spike([100, 100], [150, 150], threshold_ratio=0.10)
        assert result.flagged
        assert "increased" in result.explanation

    def test_no_data(self) -> None:
        result = diagnose_length_spike([], [])
        assert not result.flagged
        assert "no length data" in result.explanation

    def test_custom_threshold(self) -> None:
        result = diagnose_length_spike([100], [120], threshold_ratio=0.25)
        assert not result.flagged  # 20% < 25%


class TestCeiling:
    def test_no_ceiling(self) -> None:
        scores = [0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.3, 0.4]
        result = diagnose_ceiling(scores)
        assert not result.flagged

    def test_flags_ceiling(self) -> None:
        """E5: 95% of items above 90%."""
        scores = [0.95, 0.92, 0.98, 0.91, 0.99, 0.93, 0.94, 0.97, 0.96, 0.92,
                  0.93, 0.95, 0.91, 0.99, 0.98, 0.92, 0.94, 0.95, 0.93, 0.80]
        result = diagnose_ceiling(scores)
        assert result.flagged
        assert "cannot distinguish" in result.explanation

    def test_empty_scores(self) -> None:
        result = diagnose_ceiling([])
        assert not result.flagged

    def test_corpus_example(self) -> None:
        """E:177-180: if 95% of items score above 90."""
        scores = [0.95] * 95 + [0.50] * 5  # exactly 95% above 90%
        result = diagnose_ceiling(scores)
        assert result.flagged


class TestFloor:
    def test_no_floor(self) -> None:
        scores = [0.5, 0.6, 0.7, 0.8]
        result = diagnose_floor(scores)
        assert not result.flagged

    def test_flags_floor(self) -> None:
        """E6: more than 50% of items at zero."""
        scores = [0.0, 0.0, 0.0, 0.0, 0.0, 0.3]
        result = diagnose_floor(scores)
        assert result.flagged
        assert "too hard" in result.explanation

    def test_empty_scores(self) -> None:
        result = diagnose_floor([])
        assert not result.flagged

    def test_exactly_half_not_flagged(self) -> None:
        scores = [0.0, 0.0, 0.5, 0.5]
        result = diagnose_floor(scores)
        assert result.flagged  # 50% == 50% threshold (>=)


class TestRunAllDiagnostics:
    def test_returns_four_results(self) -> None:
        results = run_all_diagnostics()
        assert len(results) == 4
        kinds = {r.kind for r in results}
        assert kinds == {
            DiagnosticKind.score_jump,
            DiagnosticKind.length_spike,
            DiagnosticKind.ceiling,
            DiagnosticKind.floor,
        }

    def test_planted_reward_hack(self) -> None:
        """Gate 3: catches a planted reward hack.

        A "reward hack" is an improvement that is not real: the grader changed, or
        the output got longer (which some judges prefer), or the eval ceiling was hit.
        Run diagnostics on a scenario where length spiked and ceiling was reached.
        """
        results = run_all_diagnostics(
            regressions=0,
            improvements=50,
            total_items=100,
            lengths_before=[100] * 20,
            lengths_after=[300] * 20,
            scores=[0.95] * 96 + [0.5] * 4,
        )
        length_diag = [r for r in results if r.kind == DiagnosticKind.length_spike][0]
        ceiling_diag = [r for r in results if r.kind == DiagnosticKind.ceiling][0]
        assert length_diag.flagged, "length spike should be caught"
        assert ceiling_diag.flagged, "ceiling effect should be caught"
