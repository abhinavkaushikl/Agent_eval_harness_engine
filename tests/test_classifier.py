"""The heuristic classifier against the ten hand-written samples, and its refusals.

The samples in ``tests/fixtures/classify/`` were written before the classifier,
each with a first line ``# expect: <labels or abstain:kind> -- <why>``. That
line is the specification; the test reads it and never the other way round
(``CLAUDE.md`` §7 rule 4). Reading it is plain string handling on a comment --
the "``ast`` only" rule binds the classifier, not the test harness.

Confidences asserted below are the documented formula's outputs (units with
the signal / gradeable units), not thresholds.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from evalloop.classify import heuristics
from evalloop.classify.heuristics import (
    EMITTABLE,
    UNDETECTED,
    WITHHELD,
    Abstention,
    ClassifierResult,
    classify_file,
    classify_source,
)
from evalloop.registry.loader import RECORDS_DIR, load_records
from evalloop.vocab import Situation, parse_situation
from tests.conftest import CLASSIFY_FIXTURES_DIR, require_fixture_dir

_EXPECT = "# expect: "


def _samples() -> list[Path]:
    return sorted(require_fixture_dir(CLASSIFY_FIXTURES_DIR).glob("*.py"))


def _expectation(path: Path) -> tuple[frozenset[Situation], Abstention | None]:
    first = path.read_text(encoding="utf-8").splitlines()[0]
    assert first.startswith(_EXPECT), f"{path.name}: first line must be '{_EXPECT}... -- why'"
    spec, separator, why = first[len(_EXPECT) :].partition(" -- ")
    assert separator and why.strip(), f"{path.name}: the expect line must say why"
    if spec.startswith("abstain:"):
        return frozenset(), Abstention(spec[len("abstain:") :])
    return frozenset(parse_situation(name.strip()) for name in spec.split(",")), None


def _reached() -> frozenset[Situation]:
    return frozenset(s for record in load_records(RECORDS_DIR) for s in record.triggers_on_situation)


# -- the ten samples -------------------------------------------------------------


def test_there_are_ten_samples_each_with_a_justified_expectation() -> None:
    samples = _samples()
    assert len(samples) == 10
    for path in samples:
        _expectation(path)


@pytest.mark.parametrize("path", _samples(), ids=lambda p: p.name)
def test_each_sample_is_labelled_as_its_comment_says(path: Path) -> None:
    labels, abstention = _expectation(path)
    result = classify_file(path)
    assert result.abstention == abstention, result.reason
    assert frozenset(situation for situation, _ in result.labels) == labels, result.reason


def test_multi_label_is_two_situations_from_one_file() -> None:
    """Planner fixture 18's pair, from one route handler that runs a SELECT."""
    result = classify_file(CLASSIFY_FIXTURES_DIR / "04_fastapi_route_with_sql.py")
    assert result.labels == ((Situation.api_endpoint, 1.0), (Situation.sql_generation, 1.0))


def test_a_routes_response_model_is_not_an_extraction() -> None:
    result = classify_file(CLASSIFY_FIXTURES_DIR / "04_fastapi_route_with_sql.py")
    assert Situation.structured_extraction not in dict(result.labels)


def test_confidence_is_the_share_of_units_and_orders_the_labels() -> None:
    result = classify_file(CLASSIFY_FIXTURES_DIR / "10_mixed_module.py")
    assert result.labels == ((Situation.code_generation, 0.75), (Situation.sql_generation, 0.25))
    assert result.findings[1].reasoning == (
        "1 of 4 gradeable units: deactivate_user (UPDATE statement passed to an executor)"
    )


def test_every_label_carries_reasoning_naming_its_units() -> None:
    for path in _samples():
        result = classify_file(path)
        assert result.reason.strip()
        for finding in result.findings:
            assert "gradeable unit" in finding.reasoning


# -- determinism -----------------------------------------------------------------


@pytest.mark.parametrize("path", _samples(), ids=lambda p: p.name)
def test_same_file_same_result(path: Path) -> None:
    first = classify_file(path)
    assert classify_file(path) == first
    assert classify_source(path.read_text(encoding="utf-8"), name=path.name) == first


# -- abstention ------------------------------------------------------------------


def test_a_non_python_file_abstains_loudly(tmp_path: Path) -> None:
    script = tmp_path / "handler.ts"
    script.write_text('app.get("/users", (req, res) => res.json([]));\n', encoding="utf-8")
    result = classify_file(script)
    assert result.labels == ()
    assert result.abstention is Abstention.not_python
    assert "Python only" in result.reason and "'.ts'" in result.reason


def test_an_unreadable_file_abstains(tmp_path: Path) -> None:
    result = classify_file(tmp_path / "missing.py")
    assert result.abstention is Abstention.unreadable
    assert result.labels == ()


@pytest.mark.parametrize("source", ["def f(:\n", "x = 1\0\n", "(" * 1000 + ")" * 1000])
def test_source_that_does_not_parse_is_unclassifiable(source: str) -> None:
    result = classify_source(source, name="broken.py")
    assert result.abstention is Abstention.syntax_error
    assert result.labels == ()


def test_an_invalid_escape_warning_does_not_become_a_parse_failure() -> None:
    source = 'def pattern() -> str:\n    return "\\d+"\n'
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = classify_source(source, name="escape.py")
    assert result.labels == ((Situation.code_generation, 1.0),)


def test_a_module_with_no_functions_abstains() -> None:
    result = classify_source('"""Constants."""\nRATE = 18\n', name="constants.py")
    assert result.abstention is Abstention.no_gradeable_unit


def test_a_result_is_labels_or_an_abstention_never_both_never_neither() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        ClassifierResult((), None, "nothing")
    with pytest.raises(ValueError, match="reason"):
        ClassifierResult((), Abstention.dead_end, "  ")


# -- the six dead situations ------------------------------------------------------


def test_every_emittable_situation_reaches_a_record() -> None:
    reached = _reached()
    assert [s.value for s in EMITTABLE if s not in reached] == []


def test_the_dead_situations_are_exactly_the_withheld_and_undetected_ones() -> None:
    """If a record starts reaching one of these, this fails until the classifier is revisited."""
    dead = frozenset(Situation) - _reached()
    assert dead == frozenset(WITHHELD) | frozenset(UNDETECTED)
    assert not dead & frozenset(EMITTABLE)


def test_a_pipeline_file_abstains_naming_the_dead_end() -> None:
    source = "from airflow import DAG\n\ndef extract(day: str) -> list[str]:\n    return [day]\n"
    result = classify_source(source, name="dag.py")
    assert result.abstention is Abstention.dead_end
    assert "data_pipeline" in result.reason and "airflow" in result.reason


def test_an_ml_import_without_training_is_not_a_dead_end() -> None:
    source = "import torch\n\ndef zeros(n: int) -> torch.Tensor:\n    return torch.zeros(n)\n"
    assert classify_source(source, name="t.py").labels == ((Situation.code_generation, 1.0),)


# -- signal edges -----------------------------------------------------------------


def test_schema_inheritance_and_quoted_annotations_count() -> None:
    source = (
        "from pydantic import BaseModel\n"
        "class Base(BaseModel):\n    id: int\n"
        "class Line(Base):\n    text: str\n"
        "def lines(raw: str) -> list[Line]:\n    return [Line(id=1, text=raw)]\n"
        "def first(raw: str) -> 'Line | None':\n    return None if not raw else Line(id=1, text=raw)\n"
    )
    result = classify_source(source, name="s.py")
    assert result.labels == ((Situation.structured_extraction, 1.0),)


def test_lowercase_sql_shape_needs_an_executor() -> None:
    loose = 'def hint() -> str:\n    return "select from the list below"\n'
    executed = 'def run(c):\n    return c.execute(f"select * from {TABLE}")\n'
    assert classify_source(loose, name="a.py").labels == ((Situation.code_generation, 1.0),)
    assert classify_source(executed, name="b.py").labels == ((Situation.sql_generation, 1.0),)


def test_the_classifier_reads_the_ast_never_regex() -> None:
    text = Path(heuristics.__file__).read_text(encoding="utf-8")
    assert "import re\n" not in text and "from re " not in text
