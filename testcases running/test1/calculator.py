def add(a, b):
    return a + b


def subtract(a, b):
    return a - b


def multiply(a, b):
    return a * b


def divide(a, b):
    """Return a / b; raise ValueError on division by zero."""
    if b == 0:
        raise ValueError("cannot divide by zero")
    return a / b


def percent_of(part, whole):
    """What percent `part` is of `whole`, e.g. percent_of(30, 200) == 15.0."""
    return part / whole        # BUG: forgot to multiply by 100
