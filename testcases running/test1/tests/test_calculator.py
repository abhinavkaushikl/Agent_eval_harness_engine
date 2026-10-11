import pytest

from calculator import add, subtract, multiply, divide, percent_of


def test_add():
    assert add(2, 3) == 5


def test_subtract():
    assert subtract(10, 4) == 6


def test_multiply():
    assert multiply(6, 7) == 42


def test_divide():
    assert divide(9, 3) == 3


def test_divide_by_zero_raises():
    with pytest.raises(ValueError):
        divide(1, 0)


def test_percent_of():
    assert percent_of(30, 200) == 15.0
