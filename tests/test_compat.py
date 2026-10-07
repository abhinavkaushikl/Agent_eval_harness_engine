"""The StrEnum shim must behave exactly like ``enum.StrEnum``, on every version.

If this file fails, every situation value, tool name, record id and rendered
plan line is suspect: the M0 vocabularies are built on this one class, and a
silent spelling or rendering difference is the failure mode ``CLAUDE.md``
section 6 calls the most important correctness decision in M0.
"""

import sys

import pytest

from evalloop._compat import StrEnum


class Colour(StrEnum):
    red = "red"
    off_white = "off_white"


def test_member_is_a_real_str() -> None:
    assert isinstance(Colour.red, str)


def test_member_equals_its_value() -> None:
    assert Colour.red == "red"
    assert Colour("red") is Colour.red


def test_value_equals_lowercase_member_name() -> None:
    """The convention CLAUDE.md section 6 fixes for Situation and Tool."""
    for member in Colour:
        assert member.value == member.name


def test_str_renders_the_value_not_the_member_name() -> None:
    assert str(Colour.off_white) == "off_white"


def test_format_and_fstring_render_the_value() -> None:
    assert f"{Colour.off_white}" == "off_white"
    assert "{}".format(Colour.off_white) == "off_white"


def test_interchangeable_with_its_value_as_a_mapping_key() -> None:
    assert {"red": 1}[Colour.red] == 1


@pytest.mark.skipif(sys.version_info < (3, 11), reason="enum.StrEnum is 3.11+")
def test_matches_the_stdlib_strenum_where_it_exists() -> None:
    from enum import StrEnum as StdlibStrEnum

    class Std(StdlibStrEnum):
        off_white = "off_white"

    assert str(Std.off_white) == str(Colour.off_white)
    assert f"{Std.off_white}" == f"{Colour.off_white}"
    assert (Std.off_white == "off_white") == (Colour.off_white == "off_white")
    assert isinstance(Std.off_white, str) and isinstance(Colour.off_white, str)
