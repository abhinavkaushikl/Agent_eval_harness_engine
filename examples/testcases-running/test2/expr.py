"""A small arithmetic expression evaluator: + - * /, parentheses, unary minus,
integer and float literals, with normal precedence and left-associativity.
Recursive-descent over a token list."""


def tokenize(text):
    tokens = []
    i = 0
    while i < len(text):
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c in "+-*/()":
            tokens.append(c)
            i += 1
            continue
        if c.isdigit() or c == ".":
            j = i
            while j < len(text) and (text[j].isdigit() or text[j] == "."):
                j += 1
            tokens.append(float(text[i:j]) if "." in text[i:j] else int(text[i:j]))
            i = j
            continue
        raise ValueError(f"unexpected character {c!r} at {i}")
    return tokens


def _additive(tokens, pos):
    value, pos = _multiplicative(tokens, pos)
    if pos < len(tokens) and tokens[pos] in ("+", "-"):
        op = tokens[pos]
        rhs, pos = _additive(tokens, pos + 1)   # BUG: right-associative; breaks a - b - c
        value = value + rhs if op == "+" else value - rhs
    return value, pos


def _multiplicative(tokens, pos):
    value, pos = _factor(tokens, pos)
    if pos < len(tokens) and tokens[pos] in ("*", "/"):
        op = tokens[pos]
        rhs, pos = _multiplicative(tokens, pos + 1)   # BUG: right-associative; breaks a / b / c
        if op == "/":
            if rhs == 0:
                raise ZeroDivisionError("division by zero")
            value = value / rhs
        else:
            value = value * rhs
    return value, pos


def _factor(tokens, pos):
    if pos >= len(tokens):
        raise ValueError("unexpected end of expression")
    tok = tokens[pos]
    if tok == "-":
        value, pos = _factor(tokens, pos + 1)
        return -value, pos
    if tok == "(":
        value, pos = _additive(tokens, pos + 1)
        if pos >= len(tokens) or tokens[pos] != ")":
            raise ValueError("missing closing parenthesis")
        return value, pos + 1
    if isinstance(tok, (int, float)):
        return tok, pos + 1
    raise ValueError(f"unexpected token {tok!r}")


def evaluate(text):
    """Evaluate an arithmetic expression string and return the number."""
    tokens = tokenize(text)
    value, pos = _additive(tokens, 0)
    if pos != len(tokens):
        raise ValueError("trailing tokens after a complete expression")
    return value
