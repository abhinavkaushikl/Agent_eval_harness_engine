"""The native calibration run's id mapping (the run itself is exercised in test_run_driver.py)."""

from __future__ import annotations

from evalloop.grade.native import NativeRun, junit_key


def test_a_node_id_maps_to_junit_classname_and_name() -> None:
    assert junit_key("tests/test_a.py::test_x[1-2]") == ("tests.test_a", "test_x[1-2]")
    assert junit_key("tests/test_a.py::TestK::test_m") == ("tests.test_a.TestK", "test_m")


def test_a_synthetic_or_unknown_id_has_no_native_outcome() -> None:
    run = NativeRun({("tests.test_a", "test_x"): "passed"}, "")
    assert junit_key("tests/test_a.py") is None
    assert run.outcome_of("tests/test_a.py::test_x") == "passed"
    assert run.outcome_of("tests/test_a.py::test_y") is None
