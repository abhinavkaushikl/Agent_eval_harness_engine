"""Multi-file code: a function whose file imports other local files is graded with those files beside it.

Before this, only a module's own package went into the sandbox, so ``pricing.py`` importing a
sibling ``helpers.py`` (or another top-level package) could not import and came back undecided.
These run the real driver on small repositories built in ``tmp_path``.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from evalloop import run as driver
from evalloop.memory.case import Verdict
from evalloop.run import RunOutcome, check

TEST_TOTAL = "from pricing import total\n\ndef test_total():\n    assert total(100) == 110\n"


def _repo(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text), encoding="utf-8")
    return root


LAYOUTS = {
    "siblings": {
        "helpers.py": "def tax(x):\n    return x * 0.1\n",
        "pricing.py": "from helpers import tax\n\ndef total(x):\n    return x + tax(x)\n",
        "tests/test_pricing.py": TEST_TOTAL,
    },
    "a chain of three files": {
        "rates.py": "RATE = 0.1\n",
        "helpers.py": "from rates import RATE\n\ndef tax(x):\n    return x * RATE\n",
        "pricing.py": "import helpers\n\ndef total(x):\n    return x + helpers.tax(x)\n",
        "tests/test_pricing.py": TEST_TOTAL,
    },
    "another top-level package": {
        "util/__init__.py": "",
        "util/money.py": "def tax(x):\n    return x * 0.1\n",
        "pricing.py": "from util.money import tax\n\ndef total(x):\n    return x + tax(x)\n",
        "tests/test_pricing.py": TEST_TOTAL,
    },
    "a namespace package (no __init__.py)": {
        "util/money.py": "def tax(x):\n    return x * 0.1\n",
        "pricing.py": "from util.money import tax\n\ndef total(x):\n    return x + tax(x)\n",
        "tests/test_pricing.py": TEST_TOTAL,
    },
    "a package importing a second package": {
        "shop/__init__.py": "",
        "shop/pricing.py": "from util.money import tax\n\ndef total(x):\n    return x + tax(x)\n",
        "util/__init__.py": "",
        "util/money.py": "def tax(x):\n    return x * 0.1\n",
        "tests/test_pricing.py": "from shop.pricing import total\n\ndef test_total():\n    assert total(100) == 110\n",
    },
    "a helper the test imports itself": {
        "pricing.py": "def total(x):\n    return x * 1.1\n",
        "expected.py": "PRICES = {100: 110.00000000000001}\n",
        "tests/test_pricing.py": "from pricing import total\nfrom expected import PRICES\n\n"
                                 "def test_total():\n    assert total(100) == PRICES[100]\n",
    },
}


@pytest.mark.parametrize("layout", sorted(LAYOUTS))
def test_code_split_across_files_is_graded(tmp_path: Path, layout: str) -> None:
    result = check(_repo(tmp_path / "repo", LAYOUTS[layout]), store_dir=tmp_path / "store")
    assert result.outcome is RunOutcome.clean, [(c.artifact_id, c.verdict, c.inconclusive_reason) for c in result.cases]
    assert any(c.verdict is Verdict.passed for c in result.cases)


def test_a_bug_in_the_imported_file_fails_the_test_that_uses_it(tmp_path: Path) -> None:
    files = {**LAYOUTS["siblings"], "helpers.py": "def tax(x):\n    return x * 0.2\n"}
    result = check(_repo(tmp_path / "repo", files), store_dir=tmp_path / "store")
    assert result.outcome is RunOutcome.problem
    assert [c.verdict for c in result.cases if c.artifact_id == "pricing.py"] == [Verdict.failed]


def test_editing_the_imported_file_regrades_instead_of_reusing_the_old_verdict(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo", LAYOUTS["siblings"])
    assert check(repo, store_dir=tmp_path / "store").outcome is RunOutcome.clean
    (repo / "helpers.py").write_text("def tax(x):\n    return x * 0.2\n", encoding="utf-8")
    again = check(repo, store_dir=tmp_path / "store")
    assert again.outcome is RunOutcome.problem
    assert all(c.reused_from is None for c in again.cases if c.artifact_id == "pricing.py")


def test_test_files_never_sit_beside_the_code_under_test(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo", {
        "pricing.py": "import tests\nimport conftest\nfrom helpers import tax\n\ndef total(x):\n    return x + tax(x)\n",
        "helpers.py": "import test_secrets\n\ndef tax(x):\n    return x * 0.1\n",
        "test_secrets.py": "ANSWER = 110\n",
        "conftest.py": "",
        "tests/__init__.py": "",
        "tests/factories.py": "X = 1\n",
        "tests/test_pricing.py": "from tests.factories import X\n" + TEST_TOTAL,
    })
    context = driver._sandbox_context(repo, repo / "pricing.py", (repo / "pricing.py").read_text(),
                                      [(repo / "tests/test_pricing.py").read_text()])
    assert context is not None
    assert set(context.files) == {"pricing.py", "helpers.py"}  # no tests/, conftest.py or test_*.py


def test_nothing_local_means_nothing_extra(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo", {"pricing.py": "import json\nimport os.path\n\ndef total(x):\n    return x\n"})
    assert driver._sandbox_context(repo, repo / "pricing.py", (repo / "pricing.py").read_text(), []) is None


def test_the_closure_is_capped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    files = {f"m{i}.py": f"import m{i + 1}\nX = {i}\n" for i in range(20)}
    files["pricing.py"] = "import m0\n\ndef total(x):\n    return x\n"
    repo = _repo(tmp_path / "repo", files)
    monkeypatch.setattr(driver, "_CONTEXT_MAX_FILES", 6)
    context = driver._sandbox_context(repo, repo / "pricing.py", files["pricing.py"], [])
    assert context is not None and len(context.files) == 6


def test_a_broken_helper_is_reported_not_crashed_on(tmp_path: Path) -> None:
    files = {**LAYOUTS["siblings"], "helpers.py": "def tax(x)\n    return x\n"}  # a syntax error
    result = check(_repo(tmp_path / "repo", files), store_dir=tmp_path / "store")
    assert result.outcome in (RunOutcome.undecided, RunOutcome.problem)
    assert result.cases and all(c.artifact_id == "pricing.py" for c in result.cases)
