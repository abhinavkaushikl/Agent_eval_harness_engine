"""The oracle harvester: HIGH oracles with real provenance, from repositories that never run.

Most tests build a small repository in ``tmp_path`` so each guarantee is pinned
on its own. The done-when -- "returns HIGH-confidence oracles from a real repo"
-- runs against this repository itself, located through ``tests/conftest.py``
rather than an absolute path.
"""

from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path

import pytest

from evalloop.grade.oracles.harvest import (
    Artifact,
    BaselineStatus,
    Expectation,
    Harvest,
    HarvestError,
    Oracle,
    OracleKind,
    Provenance,
    harvest,
)
from evalloop.memory.case import CaseKind, CaseResult, FailureClass, OracleConfidence, Verdict
from evalloop.memory.metric_store import Run
from tests.conftest import REPO_ROOT

PRICING = Artifact("shop/pricing.py", "total")

BASE = {
    "shop/__init__.py": "from .pricing import total\n",
    "shop/pricing.py": """
        from dataclasses import dataclass


        @dataclass(frozen=True)
        class Receipt:
            amount: float


        def total(prices: list[float], discount: float = 0.0) -> Receipt:
            return Receipt(sum(prices) * (1 - discount))


        def unrelated(value):
            return value
    """,
    "tests/__init__.py": "",
    "tests/test_pricing.py": """
        from shop.pricing import total


        def test_total_adds() -> None:
            assert total([1.0, 2.0]).amount == 3.0


        def test_nothing_to_do_with_it() -> None:
            assert 1 + 1 == 2
    """,
}


def _repo(root: Path, files: dict[str, str]) -> Path:
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
    return root


def _ids(result: Harvest, kind: OracleKind = OracleKind.test) -> list[str]:
    return [oracle.oracle_id for oracle in result.of_kind(kind)]


def _one(result: Harvest, oracle_id: str) -> Oracle:
    (found,) = [oracle for oracle in result.oracles if oracle.oracle_id == oracle_id]
    return found


def _resolves(root: Path, oracle: Oracle) -> bool:
    """The provenance names a real line holding the thing it claims to."""
    lines = (root / oracle.provenance.path).read_text(encoding="utf-8").splitlines()
    if not 1 <= oracle.provenance.line <= oracle.provenance.end_line <= len(lines):
        return False
    text = lines[oracle.provenance.line - 1]
    name = oracle.oracle_id.rsplit("::", 1)[-1].rsplit(".", 1)[-1]
    if oracle.kind is OracleKind.schema and oracle.oracle_id.endswith(".json"):
        return True
    keyword = "class " if oracle.kind is OracleKind.schema else "def "
    return f"{keyword}{name}" in text


# -- the done-when: this repository ---------------------------------------------------------

REAL = (
    Artifact("evalloop/stats/proportions.py", "wilson_interval"),
    Artifact("evalloop/memory/episodic.py", "EpisodicStore.why"),
    Artifact("evalloop/classify/heuristics.py", "classify_source"),
)


@pytest.mark.parametrize("artifact", REAL, ids=lambda a: a.qualname)
def test_this_repository_yields_high_oracles_with_real_provenance(artifact: Artifact) -> None:
    result = harvest(REPO_ROOT, artifact)
    tests = result.of_kind(OracleKind.test)
    assert tests, result.render()
    assert result.of_kind(OracleKind.type_hints)
    for oracle in result.oracles:
        assert oracle.confidence is OracleConfidence.high
        assert _resolves(REPO_ROOT, oracle), oracle
    for oracle in tests:
        assert artifact.qualname.split(".")[-1] in oracle.evidence
    touched = [o.provenance.path for o in result.oracles] + [u.path for u in result.unsearched]
    assert not [path for path in touched if path.startswith(".")], "a dot directory was walked"


def test_the_virtualenvs_vendored_tests_are_not_this_repositorys() -> None:
    """``.venv`` holds mypy's own test_*.py files; a test that reaches them would be harvesting a stranger."""
    result = harvest(REPO_ROOT, REAL[0])
    assert result.test_files == len(list((REPO_ROOT / "tests").glob("test_*.py")))


# -- HIGH, provenance, identity -------------------------------------------------------------


def test_a_referencing_test_is_harvested_high_with_its_node_id_and_line(tmp_path: Path) -> None:
    result = harvest(_repo(tmp_path, BASE), PRICING)
    assert _ids(result) == ["tests/test_pricing.py::test_total_adds"]
    (oracle,) = result.of_kind(OracleKind.test)
    assert oracle.confidence is OracleConfidence.high
    assert oracle.provenance == Provenance("tests/test_pricing.py", 4, 5, OracleKind.test)
    assert oracle.evidence == "references total at tests/test_pricing.py:5"
    assert _resolves(tmp_path, oracle)


def test_all_three_kinds_come_back_in_order(tmp_path: Path) -> None:
    result = harvest(_repo(tmp_path, BASE), PRICING)
    assert [o.kind for o in result.oracles] == [OracleKind.test, OracleKind.schema, OracleKind.type_hints]
    schema = _one(result, "schema:shop/pricing.py::Receipt")
    assert schema.evidence == "dataclass class named by the return annotation of total"
    hints = _one(result, "type_hints:shop/pricing.py::total")
    assert hints.evidence.startswith("(prices: list[float], discount: float) -> Receipt: 2 of 2")
    assert result.reason is None and result.gaps == ()


def test_an_oracle_can_never_be_low() -> None:
    with pytest.raises(ValueError, match="HIGH"):
        Oracle(
            "x",
            Provenance("a.py", 1, 1, OracleKind.test),
            OracleConfidence.low,
            "0" * 64,
            (),
            (),
            "e",
            Expectation.none,
            (),
            BaselineStatus.no_baseline,
            "n",
        )


# -- nothing runs -------------------------------------------------------------------------


def test_harvesting_never_imports_or_runs_repository_code(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    sentinel = tmp_path / "EXECUTED"
    trap = f"open({str(sentinel)!r}, 'w').write('ran')\nraise SystemExit('repository code ran')\n"
    files = {
        "conftest.py": trap,
        "tripwire_pkg/__init__.py": trap + "from .core import compute\n",
        "tripwire_pkg/core.py": trap + "def compute(x: int) -> int:\n    return x\n",
        "tests/conftest.py": trap,
        "tests/test_core.py": trap + "from tripwire_pkg import compute\n\ndef test_compute():\n    assert compute(1) == 1\n",
    }
    before = set(sys.modules)
    result = harvest(_repo(root, files), Artifact("tripwire_pkg/core.py", "compute"))
    assert _ids(result) == ["tests/test_core.py::test_compute"]
    assert not sentinel.exists()
    assert not [name for name in set(sys.modules) - before if name.startswith(("tripwire_pkg", "conftest"))]


def test_the_harvester_has_no_way_to_run_code() -> None:
    module_file = sys.modules[harvest.__module__].__file__  # the package's `harvest` is the function
    assert module_file is not None
    source = Path(module_file).read_text(encoding="utf-8")
    for forbidden in ("importlib", "runpy", "subprocess", "__import__", "exec(", "eval(", "compile(", "pickle"):
        assert forbidden not in source, forbidden


def test_environments_vendored_code_and_symlinks_are_not_walked(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    linking = "from shop.pricing import total\n\ndef test_vendored():\n    total([1.0])\n"
    outside = tmp_path / "test_outside.py"
    outside.write_text(linking, encoding="utf-8")
    files = dict(BASE)
    files.update(
        {
            ".venv/lib/test_dot.py": linking,
            "env/pyvenv.cfg": "home = /usr/bin\n",
            "env/lib/test_venv.py": linking,
            "node_modules/pkg/test_node.py": linking,
            "lib/site-packages/test_site.py": linking,
        }
    )
    _repo(root, files)
    os.symlink(outside, root / "tests" / "test_linked.py")
    assert _ids(harvest(root, PRICING)) == ["tests/test_pricing.py::test_total_adds"]


# -- linking: precise, through imports, fixtures and helpers --------------------------------


def test_a_same_named_function_elsewhere_and_indirect_coverage_do_not_link(tmp_path: Path) -> None:
    files = dict(BASE)
    files.update(
        {
            "other/__init__.py": "",
            "other/pricing.py": "def total(x):\n    return x\n",
            "tests/test_other.py": "from other.pricing import total\n\ndef test_other():\n    assert total(1) == 1\n",
            "shop/checkout.py": "from shop.pricing import total\n\ndef checkout(p):\n    return total(p)\n",
            "tests/test_checkout.py": (
                "from shop.checkout import checkout\n\ndef test_checkout():\n    assert checkout([1.0]).amount == 1.0\n"
            ),
        }
    )
    assert _ids(harvest(_repo(tmp_path, files), PRICING)) == ["tests/test_pricing.py::test_total_adds"]


def test_every_import_style_resolves_to_the_artifact(tmp_path: Path) -> None:
    files = dict(BASE)
    files["tests/test_styles.py"] = """
        import shop
        import shop.pricing
        import shop.pricing as pricing_module
        from shop import pricing


        def test_alias():
            pricing_module.total([1.0])


        def test_package_module():
            pricing.total([1.0])


        def test_dotted():
            shop.pricing.total([1.0])


        def test_relative_reexport():
            shop.total([1.0])


        def test_local_import():
            from shop.pricing import total as priced
            priced([1.0])


        def test_shadowed_by_a_local(total=None):
            total = lambda prices: prices
            total([1.0])
    """
    result = harvest(_repo(tmp_path, files), PRICING)
    assert [i.rsplit("::", 1)[1] for i in _ids(result) if "test_styles" in i] == [
        "test_alias",
        "test_package_module",
        "test_dotted",
        "test_relative_reexport",
        "test_local_import",
    ]


def test_fixtures_and_test_side_helpers_carry_the_link(tmp_path: Path) -> None:
    files = dict(BASE)
    files.update(
        {
            "tests/conftest.py": """
                import pytest
                from shop.pricing import total


                @pytest.fixture
                def receipt():
                    return total([2.0, 3.0])
            """,
            "tests/helpers.py": "from shop.pricing import total\n\ndef priced(*prices):\n    return total(list(prices))\n",
            "tests/test_indirect.py": """
                from tests.helpers import priced


                def test_via_fixture(receipt):
                    assert receipt.amount == 5.0


                def test_via_helper():
                    assert priced(1.0).amount == 1.0


                def test_with_a_builtin_fixture(tmp_path, receipt):
                    assert receipt.amount
            """,
        }
    )
    result = harvest(_repo(tmp_path, files), PRICING)
    fixture = _one(result, "tests/test_indirect.py::test_via_fixture")
    assert fixture.evidence == "references total at tests/conftest.py:7, via fixture receipt"
    assert _one(result, "tests/test_indirect.py::test_via_helper").evidence.endswith("via helper priced")
    builtin = _one(result, "tests/test_indirect.py::test_with_a_builtin_fixture")
    assert builtin.unresolved == ("tmp_path",)
    assert {c.name for c in fixture.components} == {"test_via_fixture", "receipt"}


def test_a_method_links_through_its_class_and_the_attribute(tmp_path: Path) -> None:
    files = dict(BASE)
    files.update(
        {
            "shop/cart.py": """
                class Cart:
                    def __init__(self):
                        self.items = []

                    def add(self, price: float) -> None:
                        self.items.append(price)

                    @classmethod
                    def empty(cls) -> "Cart":
                        return cls()
            """,
            "tests/test_cart.py": """
                import pytest
                from shop.cart import Cart


                @pytest.fixture
                def cart():
                    return Cart()


                def test_add_via_fixture(cart):
                    cart.add(1.0)


                def test_classmethod():
                    assert Cart.empty().items == []


                def test_add_never_called(cart):
                    assert cart.items == []
            """,
        }
    )
    root = _repo(tmp_path, files)
    added = harvest(root, Artifact("shop/cart.py", "Cart.add"))
    assert _ids(added) == ["tests/test_cart.py::test_add_via_fixture"]
    assert _one(added, "tests/test_cart.py::test_add_via_fixture").evidence == (
        "references Cart at tests/test_cart.py:7 via fixture cart and accesses .add at tests/test_cart.py:11"
    )
    assert _one(added, "type_hints:shop/cart.py::Cart.add").evidence.startswith("(price: float) -> None")
    empty = harvest(root, Artifact("shop/cart.py", "Cart.empty"))
    assert _ids(empty) == ["tests/test_cart.py::test_classmethod"]


def test_an_autouse_fixture_that_touches_the_artifact_links_nothing(tmp_path: Path) -> None:
    files = dict(BASE)
    files["tests/test_autouse.py"] = """
        import pytest
        import shop.pricing


        @pytest.fixture(autouse=True)
        def patched(monkeypatch):
            shop.pricing.total([1.0])


        def test_something_else():
            assert True
    """
    assert _ids(harvest(_repo(tmp_path, files), PRICING)) == ["tests/test_pricing.py::test_total_adds"]


def test_unittest_cases_are_collected_and_classes_with_init_are_not(tmp_path: Path) -> None:
    files = dict(BASE)
    files["tests/test_unit.py"] = """
        import unittest
        from shop.pricing import total


        class PricingCase(unittest.TestCase):
            def setUp(self):
                self.prices = [1.0]

            def test_total(self):
                self.assertEqual(total(self.prices).amount, 1.0)

            def helper(self):
                total([2.0])


        class TestWithInit:
            def __init__(self):
                pass

            def test_never_collected(self):
                total([1.0])
    """
    result = harvest(_repo(tmp_path, files), PRICING)
    assert "tests/test_unit.py::PricingCase::test_total" in _ids(result)
    assert not [i for i in _ids(result) if "TestWithInit" in i or i.endswith("::helper")]
    case = _one(result, "tests/test_unit.py::PricingCase::test_total")
    assert {c.name for c in case.components} >= {"PricingCase.test_total", "PricingCase.setUp", "PricingCase (class)"}


def test_parametrized_arguments_are_not_fixture_requests(tmp_path: Path) -> None:
    files = dict(BASE)
    files["tests/test_params.py"] = """
        import pytest
        from shop.pricing import total


        @pytest.mark.parametrize("prices, expected", [([1.0], 1.0)])
        def test_table(prices, expected, request):
            assert total(prices).amount == expected
    """
    result = harvest(_repo(tmp_path, files), PRICING)
    assert _one(result, "tests/test_params.py::test_table").unresolved == ("request",)


# -- already failing ----------------------------------------------------------------------

MARKED = """
    import sys
    import unittest

    import pytest
    from shop.pricing import total


    @pytest.mark.xfail(reason="rounding bug")
    def test_known_bad():
        assert total([0.1, 0.2]).amount == 0.3


    @pytest.mark.skip(reason="slow")
    def test_skipped():
        total([1.0])


    @pytest.mark.skipif(True, reason="never on CI")
    def test_conditional_skip():
        total([1.0])


    @pytest.mark.xfail(sys.platform == "win32", reason="paths")
    def test_conditional_xfail():
        total([1.0])


    def test_plain():
        total([1.0])


    class TestUnit(unittest.TestCase):
        @unittest.expectedFailure
        def test_expected(self):
            total([1.0])


    @unittest.skip("broken suite")
    class SkippedSuite(unittest.TestCase):
        def test_inside(self):
            total([1.0])
"""


def test_marks_declare_what_was_already_failing_without_running_anything(tmp_path: Path) -> None:
    files = dict(BASE)
    files["tests/test_marked.py"] = MARKED
    files["tests/test_module_mark.py"] = """
        import pytest
        from shop.pricing import total

        pytestmark = [pytest.mark.xfail(reason="whole module")]


        def test_under_module_mark():
            total([1.0])
    """
    result = harvest(_repo(tmp_path, files), PRICING)
    known = _one(result, "tests/test_marked.py::test_known_bad")
    assert known.expectation is Expectation.expected_failure and known.already_failing is True
    assert known.markers == ('pytest.mark.xfail(reason="rounding bug")',)
    assert _one(result, "tests/test_marked.py::TestUnit::test_expected").already_failing is True
    assert _one(result, "tests/test_module_mark.py::test_under_module_mark").already_failing is True
    for conditional in ("test_conditional_skip", "test_conditional_xfail"):
        oracle = _one(result, f"tests/test_marked.py::{conditional}")
        assert oracle.expectation is Expectation.conditional and oracle.already_failing is None
    plain = _one(result, "tests/test_marked.py::test_plain")
    assert plain.expectation is Expectation.none and plain.already_failing is None
    assert [item.oracle_id for item in result.excluded] == [
        "tests/test_marked.py::test_skipped",
        "tests/test_marked.py::SkippedSuite::test_inside",
    ]
    assert "never runs" in result.excluded[0].reason and "pytest.mark.skip" in result.excluded[0].reason


def _case(oracle: Oracle, verdict: Verdict, *, oracle_hash: str | None = None, tag: str = "") -> CaseResult:
    return CaseResult(
        run_id="before",
        record_id="A1_execution_based",
        case_id=f"{oracle.oracle_id}{tag}",
        case_kind=CaseKind.generated,
        artifact_id=PRICING.artifact_id,
        oracle_id=oracle.oracle_id,
        oracle_confidence=OracleConfidence.high,
        ladder_rung=1,
        verdict=verdict,
        failure_class=FailureClass.wrong_result if verdict is Verdict.failed else None,
        timeout=None,
        inconclusive_reason="the sandbox crashed" if verdict is Verdict.inconclusive else None,
        score=None,
        evidence=None,
        artifact_hash="a" * 64,
        oracle_hash=oracle_hash or oracle.oracle_hash,
        reused_from=None,
        seed=None,
        cost_usd=None,
        duration_seconds=0.0,
    )


def test_a_baseline_run_identifies_failures_that_predate_the_change(tmp_path: Path) -> None:
    files = dict(BASE)
    files["tests/test_more.py"] = """
        from shop.pricing import total


        def test_a():
            total([1.0])


        def test_b():
            total([2.0])


        def test_c():
            total([3.0])


        def test_d():
            total([4.0])


        def test_e():
            total([5.0])
    """
    root = _repo(tmp_path, files)
    first = harvest(root, PRICING)
    a, b, c, d, e = (_one(first, f"tests/test_more.py::test_{x}") for x in "abcde")
    run = Run(
        "before",
        (
            _case(a, Verdict.failed),
            _case(b, Verdict.passed),
            _case(c, Verdict.failed, oracle_hash="f" * 64),
            _case(d, Verdict.inconclusive),
            _case(e, Verdict.passed, tag="#1"),
            _case(e, Verdict.failed, tag="#2"),
        ),
    )
    second = harvest(root, PRICING, baseline=run)
    expected = {
        "test_a": (BaselineStatus.failed, True),
        "test_b": (BaselineStatus.passed, False),
        "test_c": (BaselineStatus.changed, None),
        "test_d": (BaselineStatus.inconclusive, None),
        "test_e": (BaselineStatus.conflicting, None),
    }
    for name, (status, failing) in expected.items():
        oracle = _one(second, f"tests/test_more.py::{name}")
        assert (oracle.baseline, oracle.already_failing) == (status, failing), oracle.baseline_note
    assert "failed in run before with identical content (wrong_result)" in _one(second, "tests/test_more.py::test_a").baseline_note
    assert _one(second, "tests/test_pricing.py::test_total_adds").baseline is BaselineStatus.not_in_baseline
    assert _one(first, "tests/test_more.py::test_a").baseline is BaselineStatus.no_baseline
    assert "ALREADY FAILING" in second.render()


# -- what M3 can see: the oracle hash ---------------------------------------------------------

HASHED = {
    **BASE,
    "tests/conftest.py": """
        import pytest


        @pytest.fixture
        def prices():
            return [1.0, 2.0]


        @pytest.fixture(autouse=True)
        def quiet():
            yield
    """,
    "tests/test_hashed.py": """
        from shop.pricing import total

        TOLERANCE = 1e-9


        def _close(a, b):
            return abs(a - b) <= TOLERANCE


        def _unused():
            return None


        def test_sum(prices):
            assert _close(total(prices).amount, 3.0)
    """,
}
HASHED_ID = "tests/test_hashed.py::test_sum"


def _hash_after(tmp_path: Path, name: str, edits: dict[str, tuple[str, str]]) -> str:
    files = {path: textwrap.dedent(text).lstrip("\n") for path, text in HASHED.items()}  # edit flush-left text
    for path, (old, new) in edits.items():
        assert old in files[path]
        files[path] = files[path].replace(old, new)
    return _one(harvest(_repo(tmp_path / name, files), PRICING), HASHED_ID).oracle_hash


def test_the_oracle_hash_ignores_moves_and_neighbours(tmp_path: Path) -> None:
    original = _hash_after(tmp_path, "original", {})
    shifted = _hash_after(tmp_path, "shifted", {"tests/test_hashed.py": ("from shop", "# a comment\n\n\nfrom shop")})
    neighbour = _hash_after(
        tmp_path, "neighbour", {"tests/test_hashed.py": ("def test_sum", "def test_other():\n    pass\n\n\ndef test_sum")}
    )
    unused = _hash_after(tmp_path, "unused", {"tests/test_hashed.py": ("return None", "return 1")})
    assert original == shifted == neighbour == unused


@pytest.mark.parametrize(
    ("path", "old", "new"),
    [
        ("tests/test_hashed.py", "3.0)", "3.0) or True"),
        ("tests/test_hashed.py", "TOLERANCE = 1e-9", "TOLERANCE = 10"),
        ("tests/test_hashed.py", "<= TOLERANCE", "<= TOLERANCE * 2"),
        ("tests/test_hashed.py", "def test_sum", "import pytest\n@pytest.mark.xfail\ndef test_sum"),
        ("tests/conftest.py", "[1.0, 2.0]", "[3.0]"),
        ("tests/conftest.py", "yield", "yield None"),
    ],
    ids=["assertion", "constant", "helper", "xfail-added", "fixture", "autouse-fixture"],
)
def test_the_oracle_hash_changes_when_anything_the_test_depends_on_changes(
    tmp_path: Path, path: str, old: str, new: str
) -> None:
    assert _hash_after(tmp_path, "edited", {path: (old, new)}) != _hash_after(tmp_path, "original", {})


def test_components_say_which_piece_of_the_oracle_is_which(tmp_path: Path) -> None:
    oracle = _one(harvest(_repo(tmp_path, HASHED), PRICING), HASHED_ID)
    assert [(c.path, c.name) for c in oracle.components] == [
        ("tests/conftest.py", "prices"),
        ("tests/conftest.py", "quiet"),
        ("tests/test_hashed.py", "TOLERANCE"),
        ("tests/test_hashed.py", "_close"),
        ("tests/test_hashed.py", "test_sum"),
    ]


# -- schemas and type hints -----------------------------------------------------------------


def test_schemas_named_by_the_signature_and_referenced_json_schemas(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (tmp_path / "outside.schema.json").write_text('{"$schema": "https://json-schema.org/x"}', encoding="utf-8")
    files = dict(BASE)
    files.update(
        {
            "shop/models.py": """
                from enum import Enum
                from typing import TypedDict

                from pydantic import BaseModel


                class Line(TypedDict):
                    sku: str


                class Order(BaseModel):
                    lines: list[Line]


                class Rush(Order):
                    pass


                class Colour(Enum):
                    RED = 1
            """,
            "shop/extract.py": """
                from __future__ import annotations

                from shop.models import Colour, Rush

                SCHEMA = "schemas/order.schema.json"
                DATA = "data.json"
                OUTSIDE = "../outside.schema.json"
                ABSOLUTE = "/etc/order.schema.json"


                def extract(text: str, colour: Colour) -> "Rush | None":
                    return None
            """,
            "schemas/order.schema.json": '{"$schema": "https://json-schema.org/draft/2020-12/schema"}\n',
            "shop/data.json": '{"not": "a schema"}\n',
        }
    )
    result = harvest(_repo(root, files), Artifact("shop/extract.py", "extract"))
    assert _ids(result, OracleKind.schema) == ["schema:schemas/order.schema.json", "schema:shop/models.py::Rush"]
    rush = _one(result, "schema:shop/models.py::Rush")
    assert rush.evidence == "pydantic-shaped class named by the return annotation of extract"
    assert [c.name for c in rush.components] == ["Line", "Order", "Rush"]
    assert _one(result, "schema:schemas/order.schema.json").evidence == "JSON Schema referenced at shop/extract.py:5"
    for oracle in result.oracles:
        assert _resolves(root, oracle)


def test_no_annotations_means_no_type_hint_oracle(tmp_path: Path) -> None:
    files = dict(BASE)
    files["shop/legacy.py"] = "def mystery(a, b):\n    return a * b\n"
    result = harvest(_repo(tmp_path, files), Artifact("shop/legacy.py", "mystery"))
    assert result.oracles == ()
    assert [gap.kind for gap in result.gaps] == list(OracleKind)


# -- nothing is a valid answer, and it says why ------------------------------------------------


def test_no_oracle_returns_empty_with_a_reason_that_reaches_the_report(tmp_path: Path) -> None:
    files = dict(BASE)
    files["shop/legacy.py"] = "def mystery(a, b):\n    return a * b\n"
    files["tests/test_broken.py"] = "def test_half(:\n"
    result = harvest(_repo(tmp_path, files), Artifact("shop/legacy.py", "mystery"))
    assert result.oracles == ()
    assert result.reason is not None
    assert result.reason.startswith("no oracle available for shop/legacy.py::mystery: no test in the 1 test file")
    assert "1 test file(s) could not be parsed" in result.reason
    assert "has no annotations" in result.reason and "ARCHITECTURE.md §9" in result.reason
    assert result.reason in result.render()
    assert [(u.path, u.reason.split(" (")[0]) for u in result.unsearched] == [("tests/test_broken.py", "does not parse")]


def test_a_repository_without_tests_says_so(tmp_path: Path) -> None:
    files = {k: v for k, v in BASE.items() if not k.startswith("tests/")}
    result = harvest(_repo(tmp_path, files), PRICING)
    assert result.gaps[0].reason == "the repository has no test_*.py or *_test.py file"
    assert result.of_kind(OracleKind.schema) and result.of_kind(OracleKind.type_hints)


# -- determinism and refusals -----------------------------------------------------------------


def test_the_same_repository_gives_the_same_harvest(tmp_path: Path) -> None:
    files = dict(BASE)
    files["tests/test_marked.py"] = MARKED
    root = _repo(tmp_path, files)
    first = harvest(root, PRICING)
    assert harvest(root, PRICING) == first
    assert first.render() == harvest(root, PRICING).render()
    keys = [(o.kind.value, o.provenance.path, o.provenance.line) for o in first.of_kind(OracleKind.test)]
    assert keys == sorted(keys)


@pytest.mark.parametrize(
    ("artifact", "match"),
    [
        (Artifact("/abs/pricing.py", "total"), "normalised path"),
        (Artifact("../pricing.py", "total"), "normalised path"),
        (Artifact("./shop/pricing.py", "total"), "normalised path"),
        (Artifact("shop/missing.py", "total"), "not a Python file"),
        (Artifact("shop/pricing.py", "absent"), "not a top-level function"),
        (Artifact("shop/pricing.py", "Receipt"), "not a top-level function"),
        (Artifact("shop/pricing.py", "Receipt.amount.real"), "not a top-level function"),
    ],
)
def test_an_artifact_that_cannot_be_located_is_refused(tmp_path: Path, artifact: Artifact, match: str) -> None:
    with pytest.raises(HarvestError, match=match):
        harvest(_repo(tmp_path, BASE), artifact)


def test_a_root_that_is_not_a_directory_is_refused(tmp_path: Path) -> None:
    with pytest.raises(HarvestError, match="not a directory"):
        harvest(tmp_path / "nowhere", PRICING)
