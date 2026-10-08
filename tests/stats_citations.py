"""The corpus lines the statistics tests cite, and the one rule for comparing with them.

Every ``<section>:<line>`` a statistics test names in its docstring must be a
key in :data:`CITES`, and every entry is checked against the corpus file by
``tests/test_stats_corpus_examples.py``: the snippet must appear verbatim on
that line. So a citation cannot drift -- if the corpus is edited and a figure
moves, the sweep names the line rather than the test silently testing nothing.

Snippets are copied from the corpus, Unicode included (U+2212 minus, superscript
two, the middle dot). Section letters resolve to files through
``tests/conftest.SECTION_FILES``; no corpus filename is spelled here.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from types import MappingProxyType, ModuleType

__all__ = ["CITES", "Cite", "cite", "citations_in", "reads_as"]


@dataclass(frozen=True)
class Cite:
    """A corpus line and the verbatim fragments of it that a test relies on."""

    section: str
    line: int
    snippets: tuple[str, ...]


def cite(section: str, line: int, *snippets: str) -> Cite:
    return Cite(section, line, snippets)


def _table(*cites: Cite) -> Mapping[str, Cite]:
    table: dict[str, Cite] = {}
    for entry in cites:
        key = f"{entry.section}:{entry.line}"
        if key in table:
            raise ValueError(f"{key} is cited twice; put both snippets in one entry")
        table[key] = entry
    return MappingProxyType(table)


CITES: Mapping[str, Cite] = _table(
    # -- section C ----------------------------------------------------------
    cite("C", 19, "Sample size per arm ≈ 16·p(1−p) / δ²* (α = 0.05, 80% power)"),
    cite("C", 20, "the true failure rate is **≤ 3/n** at 95% confidence"),
    cite("C", 21, "which is already **64% at k = 20**"),
    cite("C", 25, "REPORT A 95% CI ON EVERY SCORE"),
    cite("C", 28, "It stays inside [0, 1], it's accurate at small n"),
    cite("C", 31, "82 of 100 has a Wilson 95% CI of **[73.3%, 88.3%]**"),
    cite("C", 35, "Use Wilson, not the textbook ±1.96·√(p(1−p)/n)."),
    cite("C", 49, "Wilson CIs were **[83.8, 97.9]** and **[73.8, 93.0]**"),
    cite("C", 62, "given your budget of n, compute the **minimum detectable effect (MDE)**"),
    cite("C", 65, "detecting 80% → 85% needs ≈ 920 items per arm", "it drops to **≈ 375**"),
    cite("C", 69, "n ≈ 16·p(1−p)/δ² per arm"),
    cite("C", 70, "n ≈ (1.96·√d + 0.84·√(d − δ²))² / δ²"),
    cite("C", 79, "at n = 150 per arm, the chance of detecting a real 5-point gain was **21%**"),
    cite("C", 84, "Detecting 2 points with 10% discordance needs **≈ 1,960 paired items**", "The MDE at 300 was about 5 points."),
    cite("C", 94, "k ≥ 5 RUNS PER ITEM"),
    cite("C", 97, "The run-to-run SD is your noise floor."),
    cite("C", 100, "76.1, 79.4, 77.8, 74.9 and 78.2. The mean is 77.3 and the SD is 1.8", "they span 4.5 points"),
    cite("C", 103, "**Run k = 5** for decisions and k = 3 for daily iteration"),
    cite("C", 104, "**Report mean ± SD** and the per-run numbers."),
    cite("C", 118, "84.1, 82.0 and 83.5, a 2.1-point spread"),
    cite("C", 132, "the 95% upper bound on the true rate is approximately **3/n**"),
    cite("C", 135, "For 198/200 it gives **[97.6%, 100.4%]**, which is impossible", "Wilson for 198/200 gives **[96.4%, 99.7%]**"),
    cite("C", 138, "0/300 → ≤ 1.0% at 95%"),
    cite("C", 139, "To claim ≤ 0.1% you need **3,000 clean items**, and to claim ≤ 0.01% you need 30,000"),
    cite("C", 140, "wants a conservative exact interval. Use Wilson otherwise."),
    cite("C", 147, '"99.0% ± 1.4"'),
    cite("C", 169, "P(at least one false alarm) = 1 − 0.95²⁰ = **64%**"),
    cite("C", 188, "Twelve comparisons at α = 0.05 each gave a 46% chance of at least one false win"),
    cite("C", 201, "the fraction of shuffles whose difference is at least as large as the one you observed"),
    cite("C", 207, "Use the median or a 10% trimmed mean for heavy tails"),
    cite("C", 208, "flip the sign of each item's difference at random"),
    cite("C", 209, "The smallest p-value you can report is 1/10,000."),
    cite("C", 217, "p = 0.018** (180 of 10,000 shuffles were as extreme)"),
    # -- section B ----------------------------------------------------------
    cite("B", 22, "At n = 100 that's ±10, at n = 400 it's ±5, and at n = 2,500 it's ±2."),
    cite("B", 37, "draw 5,000 resamples of item IDs"),
    cite("B", 100, "With continuity correction, χ² = (|b − c| − 1)² / (b + c)"),
    cite("B", 107, "At least 25 discordant pairs (b + c ≥ 25) are needed for the χ² approximation."),
    cite("B", 108, "Compare it with 3.84 (p = 0.05) or 6.63 (p = 0.01)."),
    cite("B", 116, "χ² = (|40 − 65| − 1)² / 105 = **5.49, p ≈ 0.019**"),
    cite("B", 120, "88.0% vs 90.7%, with b = 3 and c = 11."),
    cite(
        "B",
        121,
        "uncorrected χ² = 64/14 = 4.57 and got **p = 0.033**",
        "The exact binomial gives **p = 0.057**",
        "(b = 8, c = 21), got p = 0.03 by McNemar",
    ),
    cite("B", 169, "SE = √(p(1−p)/n), and the 95% margin is ±1.96·SE"),
    cite("B", 172, "At n = 500 and p = 0.85, SE = 1.6 points, so the margin is ±3.1."),
    cite("B", 190, "At n = 120 and p ≈ 0.8, the margin is **±7.2 points**.", "giving a margin of ±3.2"),
    cite("B", 211, "**Use 5,000 resamples for reporting** and 1,000 while iterating."),
    cite("B", 213, "**Fix the random seed** so the CI is reproducible in the review."),
    cite("B", 243, "With m = 10 and ρ = 0.4, 1,000 questions carry the information of only **217**."),
    cite("B", 247, "**Resample cluster IDs with replacement** and include all items from each chosen cluster."),
    cite("B", 248, "A ratio above about 1.5× means clustering matters"),
    cite("B", 254, "QA over 100 vendor contracts, 10 questions each"),
    cite("B", 256, "With item-level CI ±2.4, it looked significant."),
    cite("B", 257, "The cluster CI was **±5.1**, the same 2.1× widening the design-effect formula predicts at ρ = 0.4"),
    cite("B", 260, "2,000 bot turns from 250 conversations"),
    cite("B", 261, '86% correct, reported as "86 ± 1.5".'),
    cite("B", 262, "71% ± 5.6 on 250 conversations"),
)

#: A citation as the tests write it: one section letter, a colon, a line number.
_CITATION = re.compile(r"\b([A-J]):(\d+)\b")


def citations_in(module: ModuleType) -> dict[str, list[str]]:
    """Every ``<section>:<line>`` named in a test docstring, mapped to the tests naming it."""
    found: dict[str, list[str]] = {}
    for name in sorted(vars(module)):
        test = vars(module)[name]
        if not (name.startswith("test_") and callable(test)) or not test.__doc__:
            continue
        for section, line in _CITATION.findall(test.__doc__):
            found.setdefault(f"{section}:{line}", []).append(name)
    return found


def reads_as(value: float, printed: str) -> bool:
    """Does ``value`` read as the corpus's ``printed`` figure?

    The one rounding rule for every comparison with the corpus: round ``value``
    half-up to the number of decimal places ``printed`` has, and compare. So
    ``reads_as(73.3326, "73.3")`` holds and ``reads_as(73.36, "73.3")`` does not.
    ``printed`` is the corpus figure with any ``%``, ``±`` or thousands comma
    removed, and nothing else changed.
    """
    places = len(printed.split(".")[1]) if "." in printed else 0
    quantum = Decimal(1).scaleb(-places)
    return Decimal(repr(value)).quantize(quantum, rounding=ROUND_HALF_UP) == Decimal(printed)
