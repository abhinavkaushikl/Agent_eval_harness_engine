"""A simple calculator. Deliberately has NO tests — watch the bot write them."""


def add(a: float, b: float) -> float:
    """Return the sum of a and b."""
    return a + b


def subtract(a: float, b: float) -> float:
    """Return a minus b."""
    return a - b


def multiply(a: float, b: float) -> float:
    """Return the product of a and b."""
    return a * b


def divide(a: float, b: float) -> float:
    """Return a divided by b. Dividing by zero raises ValueError."""
    if b == 0:
        raise ValueError("cannot divide by zero")
    return a / b
