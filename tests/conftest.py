"""Shared fixtures, and the single source of truth for corpus file names.

The methodology corpus is versioned inside this repository, in the top-level
``knowledge rules`` directory (decision EL-001). ``corpus_dir`` therefore
defaults to that directory, resolved relative to the repo root rather than
written out as an absolute user path. ``EVALLOOP_CORPUS`` still overrides it,
so the corpus can be pointed at a checkout elsewhere.

Every corpus filename in this project is declared here once. Nothing else in
the test suite or the package may spell a corpus filename literally: a single
silent mismatch is exactly the failure mode this module exists to prevent.
``SECTION_TITLES`` is shared by both header forms, because the master lookup
("## A. CHOOSING HOW TO GRADE") and the deep dive ("# SECTION A - CHOOSING HOW
TO GRADE", with an en dash) use the same title text.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIRNAME = "knowledge rules"
DEFAULT_CORPUS_DIR = REPO_ROOT / CORPUS_DIRNAME
CORPUS_ENV_VAR = "EVALLOOP_CORPUS"

MASTER_LOOKUP = "evals-situation-to-technique.md"
INDEX_FILE = "00-INDEX.md"

SECTION_FILES: Mapping[str, str] = MappingProxyType(
    {
        "A": "A-choosing-how-to-grade.md",
        "B": "B-comparing-two-things.md",
        "C": "C-deciding-whether-a-result-is-real.md",
        "D": "D-rare-events.md",
        "E": "E-when-a-number-looks-wrong.md",
        "F": "F-trusting-your-grader.md",
        "G": "G-rag-systems.md",
        "H": "H-agents.md",
        "I": "I-production.md",
        "J": "J-choosing-a-model.md",
    }
)

SECTION_TITLES: Mapping[str, str] = MappingProxyType(
    {
        "A": "CHOOSING HOW TO GRADE",
        "B": "COMPARING TWO THINGS",
        "C": "DECIDING WHETHER A RESULT IS REAL",
        "D": "RARE EVENTS",
        "E": "WHEN A NUMBER LOOKS WRONG",
        "F": "TRUSTING YOUR GRADER",
        "G": "RAG SYSTEMS",
        "H": "AGENTS",
        "I": "PRODUCTION",
        "J": "CHOOSING A MODEL",
    }
)

#: Every file the corpus must contain, in a stable order.
CORPUS_FILES: tuple[str, ...] = (MASTER_LOOKUP, INDEX_FILE, *SECTION_FILES.values())


def master_lookup_header(section: str) -> str:
    """The section header as the master lookup writes it."""
    return f"## {section}. {SECTION_TITLES[section]}"


def deep_dive_header(section: str) -> str:
    """The title header as a deep-dive file writes it (en dash, not hyphen)."""
    return f"# SECTION {section} – {SECTION_TITLES[section]}"


def missing_corpus_files(corpus_dir: Path, names: tuple[str, ...] = CORPUS_FILES) -> list[str]:
    """Names from ``names`` that are not readable files under ``corpus_dir``."""
    return [name for name in names if not (corpus_dir / name).is_file()]


def require_corpus_files(corpus_dir: Path, names: tuple[str, ...] = CORPUS_FILES) -> None:
    """Fail when the canonical corpus is incomplete; skip only when redirected.

    A missing file under the in-repo default is a real defect and must fail
    loudly, naming every file that is absent. When ``EVALLOOP_CORPUS`` points
    somewhere else entirely, that is the user's choice of a different corpus,
    so the test skips -- but the message still names what was missing and
    where it looked.
    """
    missing = missing_corpus_files(corpus_dir, names)
    if not missing:
        return
    detail = ", ".join(missing)
    override = os.environ.get(CORPUS_ENV_VAR)
    if override is not None:
        pytest.skip(
            f"{CORPUS_ENV_VAR}={override} points at {corpus_dir}, which is not a "
            f"complete corpus: missing {len(missing)} file(s): {detail}. "
            f"Looked in {corpus_dir}."
        )
    pytest.fail(
        f"corpus incomplete: {len(missing)} file(s) missing from {corpus_dir}: {detail}. "
        f"The canonical corpus is the repo's {CORPUS_DIRNAME!r} directory; "
        f"set {CORPUS_ENV_VAR} to use a corpus elsewhere."
    )


@pytest.fixture(scope="session")
def corpus_dir() -> Path:
    override = os.environ.get(CORPUS_ENV_VAR)
    if override is None:
        return DEFAULT_CORPUS_DIR
    return Path(override).expanduser()
