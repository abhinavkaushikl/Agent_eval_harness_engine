"""Standard-library compatibility for the Python 3.10 floor.

``enum.StrEnum`` arrived in 3.11, and EvalLoop supports 3.10+ (decision
``decisions/EL-012-python-version-floor.md``). Two bridges were available:
branch on ``sys.version_info`` and use the stdlib class where it exists, or
define one base class used on every version.

This module defines one. A version branch would mean the vocabulary enums --
the most correctness-critical code in M0, per ``CLAUDE.md`` section 6 -- rest on
a *different* base class depending on the interpreter, so any behavioural
difference between the two would surface as a matching bug on one machine and
not another. One definition is deterministic across versions, which
``CLAUDE.md`` section 7.8 requires, and it costs one small class.

The behaviour being matched is ``enum.StrEnum``'s: members are real ``str``
objects, compare equal to their value, and render as their value.
``tests/test_compat.py`` asserts that, and on 3.11+ asserts it side by side
against the stdlib class.
"""

from __future__ import annotations

from enum import Enum

__all__ = ["StrEnum"]


class StrEnum(str, Enum):
    """A ``str`` enum whose members render as their value on 3.10 through 3.13+.

    ``Enum`` supplies a ``__str__`` of ``"<Class>.<MEMBER>"``, which is wrong for
    a value-carrying vocabulary: a record file, an error message and a rendered
    plan line all need the value. 3.11 also changed how mixed-in enums format
    themselves, so ``__str__`` and ``__format__`` are pinned here rather than
    inherited -- that is what keeps one spelling of a situation across versions.
    """

    def __str__(self) -> str:
        return str.__str__(self)

    def __format__(self, format_spec: str) -> str:
        return str.__format__(self, format_spec)
