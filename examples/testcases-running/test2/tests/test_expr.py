import pytest

from expr import evaluate, tokenize


def test_single_number():
    assert evaluate("42") == 42


def test_addition():
    assert evaluate("2 + 3") == 5


def test_precedence_mul_over_add():
    assert evaluate("2 + 3 * 4") == 14


def test_parentheses():
    assert evaluate("(2 + 3) * 4") == 20


def test_unary_minus():
    assert evaluate("-5 + 2") == -3


def test_nested_parens():
    assert evaluate("((1 + 2) * (3 + 4))") == 21


def test_float_literals():
    assert evaluate("3.5 * 2") == 7.0


def test_whitespace_is_ignored():
    assert evaluate("  7*6 ") == 42


def test_left_assoc_subtraction():
    assert evaluate("10 - 3 - 2") == 5        # (10-3)-2, NOT 10-(3-2)=9


def test_left_assoc_division():
    assert evaluate("100 / 5 / 2") == 10      # (100/5)/2, NOT 100/(5/2)=40


def test_mixed_chain():
    assert evaluate("20 - 5 - 4 - 1") == 10   # left to right


def test_division_by_zero_raises():
    with pytest.raises(ZeroDivisionError):
        evaluate("1 / 0")


def test_bad_character_raises():
    with pytest.raises(ValueError):
        evaluate("2 $ 3")


def test_missing_paren_raises():
    with pytest.raises(ValueError):
        evaluate("(1 + 2")


def test_tokenize_basic():
    assert tokenize("1 + 2") == [1, "+", 2]
