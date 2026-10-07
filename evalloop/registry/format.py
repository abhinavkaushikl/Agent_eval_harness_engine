"""The on-disk record format: a deliberately small, strict YAML subset.

The choice, and what it costs
-----------------------------
``CLAUDE.md`` section 3 forbids PyYAML, so the options were a hand-written YAML
subset or JSON. **This is the YAML subset.** JSON was rejected on one ground:
73 records and 20 fixtures are *hand-authored and hand-reviewed*, and five of
the 22 ``TechniqueRecord`` fields are prose copied verbatim from the corpus
(``anti_pattern``, ``worked_example``, ``domain_scenario``, ``rule_of_thumb``,
``extraction_notes``). JSON has no multi-line string, so every one of those
would become a single line with ``\\n`` escapes, where a reviewer cannot see
whether the text matches the source. Comments also matter here: the fixtures
carry authoring notes such as ``# order matters``, and JSON has none.

What the subset costs: this file, roughly 300 lines that have to be right,
versus zero for ``json.loads``. The cost is paid down two ways. Everything
outside the subset **raises**, naming the line and the construct, so the parser
can never half-understand a file; and the subset is *meant* to be a true
subset -- every construct below follows YAML 1.2 semantics, chomping included,
so PyYAML could in principle replace this module without re-authoring a single
record. That intent is why the chomping rules are faithful rather than
convenient. It is checked by hand against the spec and **not** differentially:
PyYAML cannot be a dev dependency here (``CLAUDE.md`` section 3), so nothing in
the suite proves the equivalence. Where YAML's own meaning is subtle or
version-dependent, this parser refuses rather than guesses.

Supported, and nothing else
---------------------------
This list comes from the two consumers: the record files (EL-110 onward) and
the 20 planner fixtures, whose format is fixed by ``TASKS.md`` group 6.

* **Block maps**, nested to any depth by indentation (the fixtures need three
  levels: ``expect`` -> ``pending`` -> ``B3_mcnemar``). Any consistent indent
  width works; inconsistent siblings raise.
* **Inline flow lists** -- ``situations: [summarization]``, ``[]``. Items are
  scalars. Splitting is quote-aware, so ``["needs paired_runs: 2, have 1"]`` is
  one item.
* **Inline flow maps** -- ``evidence: {samples: 1, runs: 1}``, ``{}``.
* **Trailing comments** -- ``ready: [...]   # order matters`` -- and whole-line
  comments, and blank lines.
* **Quoted strings**, double or single, which is how a value containing ``": "``
  is written: ``"needs paired_runs: 2, have 1"``. Double-quoted supports
  ``\\"``, ``\\\\``, ``\\n`` and ``\\t``; single-quoted uses ``''`` for a quote.
* **Block scalars** for prose -- ``|``, ``>``, ``|-``, ``>-``. Literal keeps
  newlines, folded turns them into spaces, and the trailing newline follows
  YAML: clip (no indicator) keeps exactly one, strip (``-``) keeps none.
  ``>-`` is the one to use for record prose, because ``worked_example`` is
  printed inline on one rendered plan line.
* **Scalars** -- decimal ``int``, decimal ``float``, ``true``, ``false``,
  ``null``, and plain or quoted strings.

``float`` is supported although ``CLAUDE.md`` section 6 types ``requires`` as
``Mapping[str, int | bool]``. The corpus has float thresholds (section F's
``κ ≥ 0.6``, ``α < 0.667``), so a parser that rejected ``0.6`` would force an
author to invent ``60``. The field's type is EL-107's problem and is raised in
this ticket's report, not worked around here.

Rejected on purpose
-------------------
Each of these raises ``FormatError`` naming the line, the construct and the way
to write it instead. The rule behind the list: anything whose YAML meaning is
subtle, ambiguous, or version-dependent is refused rather than guessed.

* **Block sequences** (``- item``). Not needed by either consumer -- the
  fixtures use flow lists and record id tuples are short -- and adding a
  construct later invalidates no existing file, so this stays out until a
  consumer needs it (the monotone-widening argument of EL-002).
* **``yes``/``no``/``on``/``off``** and ``True``/``NULL``/``~``. YAML 1.1 makes
  the first group booleans and YAML 1.2 makes them strings, so either reading
  is a divergence from some real parser. Write ``true``/``false``, or quote it.
* **Numeric-looking scalars that are not plain decimals** -- ``0x10``, ``1e5``,
  ``012``, ``2026-10-07``. A real YAML parser turns these into ints, floats or
  dates; refusing them keeps this a subset. Quote them to mean the text.
* **Nested flow collections** (``[[a]]``, ``{k: [a]}``), **anchors and
  aliases** (``&a``, ``*a``, ``<<:``), **document markers** (``---``, ``...``),
  **tab indentation**, **quoted keys**, **duplicate keys**, **``|+`` keep
  chomping**, and a **more-indented line inside a block scalar** (where YAML's
  folding rules stop being obvious).

``load`` is pure: it takes text, touches no file, and returns a new ``dict``
whose key order is the file's order, so two loads of one string are equal and
rendering downstream is stable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import NoReturn

__all__ = ["FormatError", "Node", "Scalar", "load"]

Scalar = str | int | float | bool | None
Node = Scalar | list[Scalar] | dict[str, "Node"]

_KEY_VALUE = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*)[ \t]*:(?P<rest>.*)$")
_KEY_ONLY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_INT = re.compile(r"^-?(?:0|[1-9][0-9]*)$")
_FLOAT = re.compile(r"^-?(?:0|[1-9][0-9]*)\.[0-9]+$")
#: One word starting like a number. Anything here that is not _INT/_FLOAT is refused.
_NUMBERISH = re.compile(r"^[-+.0-9][^\s]*$")
_BLOCK_SCALAR = re.compile(r"^(?P<style>[|>])(?P<chomp>[-+]?)$")
_RESERVED = {
    "yes", "Yes", "YES", "no", "No", "NO",
    "on", "On", "ON", "off", "Off", "OFF",
    "True", "TRUE", "False", "FALSE",
    "Null", "NULL", "~",
}
_ESCAPES = {'"': '"', "\\": "\\", "n": "\n", "t": "\t"}


class FormatError(ValueError):
    """A construct outside the supported subset, or a malformed one.

    Carries ``line`` and ``construct`` so EL-108's loader can aggregate these
    across files without re-parsing the message.
    """

    def __init__(self, line: int, construct: str, detail: str, text: str | None = None) -> None:
        self.line = line
        self.construct = construct
        self.detail = detail
        shown = "" if text is None else f" -- {text.strip()!r}"
        super().__init__(f"line {line}: {construct}: {detail}{shown}")


@dataclass(frozen=True)
class _Line:
    number: int
    indent: int
    body: str
    raw: str

    @property
    def blank(self) -> bool:
        return not self.body

    @property
    def comment(self) -> bool:
        return self.body.startswith("#")

    @property
    def skippable(self) -> bool:
        return self.blank or self.comment


def load(text: str) -> dict[str, Node]:
    """Parse one record or fixture document into a ``dict``.

    Pure and deterministic: no file I/O, and key order follows the file.
    Raises ``FormatError`` for anything outside the documented subset.
    """
    lines = _scan(text)
    first = next((ln for ln in lines if not ln.skippable), None)
    if first is None:
        raise FormatError(1, "empty document", "no keys found; a record file must be a block map")
    if first.indent != 0:
        raise FormatError(first.number, "indentation", "the document must start at column 0", first.raw)
    if not _KEY_VALUE.match(first.body):
        _reject_unparsable(
            first,
            "top-level value",
            "the document must be a block map of 'key: value' lines",
        )
    mapping, _ = _parse_map(lines, lines.index(first), 0)
    return mapping


def _scan(text: str) -> list[_Line]:
    scanned: list[_Line] = []
    for number, raw in enumerate(text.splitlines(), 1):
        leading = raw[: len(raw) - len(raw.lstrip())]
        if "\t" in leading:
            raise FormatError(number, "tab", "tabs cannot be used for indentation; use spaces", raw)
        indent = len(leading)
        body = raw.strip()
        if body in {"---", "..."}:
            raise FormatError(number, "document marker", "multi-document files are not supported", raw)
        scanned.append(_Line(number=number, indent=indent, body=body, raw=raw))
    return scanned


def _parse_map(lines: list[_Line], index: int, indent: int) -> tuple[dict[str, Node], int]:
    mapping: dict[str, Node] = {}
    while index < len(lines):
        line = lines[index]
        if line.skippable:
            index += 1
            continue
        if line.indent < indent:
            break
        if line.indent > indent:
            raise FormatError(line.number, "indentation", f"expected indent {indent}, found {line.indent}", line.raw)
        match = _KEY_VALUE.match(line.body)
        if match is None:
            _reject_unparsable(line)
        key = match.group("key")
        if key in mapping:
            raise FormatError(line.number, "duplicate key", f"{key!r} is already set in this map", line.raw)
        rest = _strip_comment(match.group("rest"), line).strip()
        if rest == "":
            mapping[key], index = _parse_nested(lines, index, indent, key)
            continue
        block = _BLOCK_SCALAR.match(rest)
        if block is not None:
            mapping[key], index = _parse_block_scalar(lines, index, indent, block, line)
            continue
        if rest[0] in "|>":
            raise FormatError(
                line.number,
                "block scalar",
                f"unsupported indicator {rest!r}; use |, >, |- or >-",
                line.raw,
            )
        mapping[key] = _parse_value(rest, line)
        index += 1
    return mapping, index


def _reject_unparsable(
    line: _Line,
    fallback_construct: str = "syntax",
    fallback_detail: str = "expected 'key: value' or 'key:'",
) -> NoReturn:
    """Name the construct behind a line that is not ``key: value``."""
    body = line.body
    if body.startswith("- "):
        raise FormatError(
            line.number,
            "block sequence",
            "block sequences are outside the subset; write an inline flow list, [a, b]",
            line.raw,
        )
    if body.startswith(("&", "*")):
        raise FormatError(line.number, "anchor or alias", "anchors and aliases are not supported", line.raw)
    if body.startswith("<<"):
        raise FormatError(line.number, "merge key", "merge keys are not supported", line.raw)
    if body.startswith(("'", '"')):
        raise FormatError(line.number, "quoted key", "keys must be plain [A-Za-z_][A-Za-z0-9_]*", line.raw)
    raise FormatError(line.number, fallback_construct, fallback_detail, line.raw)


def _parse_nested(
    lines: list[_Line], index: int, indent: int, key: str
) -> tuple[dict[str, Node], int]:
    child_index = next(
        (offset for offset, ln in enumerate(lines[index + 1 :], index + 1) if not ln.skippable),
        None,
    )
    if child_index is None or lines[child_index].indent <= indent:
        raise FormatError(
            lines[index].number,
            "missing value",
            f"{key!r} has no value and no indented block; write {{}} for an empty map",
            lines[index].raw,
        )
    return _parse_map(lines, child_index, lines[child_index].indent)


def _parse_block_scalar(
    lines: list[_Line], index: int, indent: int, block: re.Match[str], line: _Line
) -> tuple[str, int]:
    if block.group("chomp") == "+":
        raise FormatError(line.number, "block scalar", "'+' (keep) chomping is not supported; use | or |-", line.raw)
    folded = block.group("style") == ">"
    strip = block.group("chomp") == "-"
    index += 1
    content: list[str] = []
    body_indent: int | None = None
    while index < len(lines):
        current = lines[index]
        if current.blank:
            content.append("")
            index += 1
            continue
        if current.indent <= indent:
            break
        if body_indent is None:
            body_indent = current.indent
        elif current.indent > body_indent:
            raise FormatError(
                current.number,
                "block scalar",
                "a more-indented line inside a block scalar is not supported; keep one indent level",
                current.raw,
            )
        elif current.indent < body_indent:
            raise FormatError(
                current.number,
                "block scalar",
                f"expected indent {body_indent}, found {current.indent}",
                current.raw,
            )
        content.append(current.raw[current.indent :].rstrip())
        index += 1
    while content and content[-1] == "":
        content.pop()
    if not content:
        raise FormatError(line.number, "block scalar", "the block is empty", line.raw)
    return _join_block(content, folded) + ("" if strip else "\n"), index


def _join_block(content: list[str], folded: bool) -> str:
    if not folded:
        return "\n".join(content)
    out = ""
    for piece in content:
        if piece == "":
            out += "\n"
        elif out == "" or out.endswith("\n"):
            out += piece
        else:
            out += " " + piece
    return out


def _parse_value(rest: str, line: _Line) -> Node:
    if rest.startswith("["):
        return _parse_flow_list(rest, line)
    if rest.startswith("{"):
        return _parse_flow_map(rest, line)
    return _parse_scalar(rest, line)


def _parse_flow_list(rest: str, line: _Line) -> list[Scalar]:
    inner = _flow_inner(rest, "[", "]", "flow list", line)
    if inner == "":
        return []
    return [_parse_scalar(item, line) for item in _split_flow(inner, line)]


def _parse_flow_map(rest: str, line: _Line) -> dict[str, Node]:
    inner = _flow_inner(rest, "{", "}", "flow map", line)
    if inner == "":
        return {}
    out: dict[str, Node] = {}
    for item in _split_flow(inner, line):
        key, sep, value = item.partition(":")
        if not sep:
            raise FormatError(line.number, "flow map", f"entry {item.strip()!r} has no ':'", line.raw)
        name = key.strip()
        if _KEY_ONLY.match(name) is None:
            raise FormatError(line.number, "flow map", f"key {name!r} is not a plain key", line.raw)
        if name in out:
            raise FormatError(line.number, "duplicate key", f"{name!r} is already set in this flow map", line.raw)
        out[name] = _parse_scalar(value.strip(), line)
    return out


def _flow_inner(rest: str, open_c: str, close_c: str, construct: str, line: _Line) -> str:
    if not rest.endswith(close_c):
        raise FormatError(line.number, construct, f"missing closing {close_c!r}", line.raw)
    inner = rest[1:-1]
    masked = _outside_quotes(inner, line)
    if any(char in masked for char in "[]{}"):
        raise FormatError(
            line.number,
            construct,
            "nested flow collections are not supported; use an indented block map",
            line.raw,
        )
    return inner.strip()


def _outside_quotes(text: str, line: _Line) -> str:
    """``text`` with quoted spans blanked out, for scanning structure safely.

    A quote only opens a span where a value may start -- at the beginning, or
    after ``,``, ``[``, ``{`` or ``:``. YAML allows a quote inside a plain
    scalar anywhere but the first character, and the corpus prose this parser
    carries is full of apostrophes ("Agents say \"Done\"", "someone else's
    leaderboard"), so treating every quote as a delimiter would break on them.
    """
    out: list[str] = []
    quote: str | None = None
    at_value_start = True
    index = 0
    while index < len(text):
        char = text[index]
        if quote is not None:
            if quote == '"' and char == "\\" and index + 1 < len(text):
                out.append("  ")
                index += 2
                continue
            if quote == "'" and char == "'" and text[index + 1 : index + 2] == "'":
                out.append("  ")
                index += 2
                continue
            out.append(" ")
            if char == quote:
                quote = None
            index += 1
            continue
        if at_value_start and char in "\"'":
            quote = char
            out.append(" ")
            index += 1
            continue
        out.append(char)
        if char in ",[{:":
            at_value_start = True
        elif char not in " \t":
            at_value_start = False
        index += 1
    if quote is not None:
        raise FormatError(line.number, "quoting", f"unterminated {quote} string", line.raw)
    return "".join(out)


def _split_flow(inner: str, line: _Line) -> list[str]:
    masked = _outside_quotes(inner, line)
    items: list[str] = []
    start = 0
    for position, char in enumerate(masked):
        if char == ",":
            items.append(inner[start:position])
            start = position + 1
    items.append(inner[start:])
    stripped = [item.strip() for item in items]
    if any(item == "" for item in stripped):
        raise FormatError(line.number, "flow collection", "empty entry (a trailing or doubled comma)", line.raw)
    return stripped


def _strip_comment(text: str, line: _Line) -> str:
    masked = _outside_quotes(text, line)
    position = masked.find("#")
    while position != -1:
        if position == 0 or masked[position - 1] in " \t":
            return text[:position]
        position = masked.find("#", position + 1)
    return text


def _parse_scalar(raw: str, line: _Line) -> Scalar:
    text = raw.strip()
    if text.startswith('"'):
        return _parse_double_quoted(text, line)
    if text.startswith("'"):
        return _parse_single_quoted(text, line)
    if text[:1] in "&*":
        raise FormatError(
            line.number,
            "anchor or alias",
            "anchors and aliases are not supported; write the value out",
            line.raw,
        )
    if text[:1] in "!%@`":
        raise FormatError(
            line.number,
            "reserved indicator",
            f"a plain scalar cannot start with {text[0]!r}; quote it",
            line.raw,
        )
    if text in _RESERVED:
        raise FormatError(
            line.number,
            "ambiguous scalar",
            f"{text!r} means different things in YAML 1.1 and 1.2; write true/false/null, or quote it",
            line.raw,
        )
    if text == "true":
        return True
    if text == "false":
        return False
    if text == "null":
        return None
    if _INT.match(text):
        return int(text)
    if _FLOAT.match(text):
        return float(text)
    if _NUMBERISH.match(text):
        raise FormatError(
            line.number,
            "ambiguous scalar",
            f"{text!r} is not a plain decimal; a YAML parser would read it as a number or date. Quote it",
            line.raw,
        )
    if ": " in text:
        raise FormatError(
            line.number,
            "ambiguous scalar",
            "a plain string containing ': ' is ambiguous; wrap it in double quotes",
            line.raw,
        )
    return text


def _parse_double_quoted(text: str, line: _Line) -> str:
    if len(text) < 2 or not text.endswith('"'):
        raise FormatError(line.number, "quoting", "unterminated \" string", line.raw)
    out: list[str] = []
    index = 1
    end = len(text) - 1
    while index < end:
        char = text[index]
        if char == "\\":
            if index + 1 >= end:
                raise FormatError(line.number, "quoting", "trailing backslash", line.raw)
            following = text[index + 1]
            if following not in _ESCAPES:
                raise FormatError(
                    line.number,
                    "escape",
                    f"\\{following} is not supported; only \\\\, \\\", \\n and \\t are",
                    line.raw,
                )
            out.append(_ESCAPES[following])
            index += 2
            continue
        if char == '"':
            raise FormatError(line.number, "quoting", "unescaped \" inside a double-quoted string", line.raw)
        out.append(char)
        index += 1
    return "".join(out)


def _parse_single_quoted(text: str, line: _Line) -> str:
    if len(text) < 2 or not text.endswith("'"):
        raise FormatError(line.number, "quoting", "unterminated ' string", line.raw)
    inner = text[1:-1]
    out: list[str] = []
    index = 0
    while index < len(inner):
        if inner[index] == "'":
            if index + 1 < len(inner) and inner[index + 1] == "'":
                out.append("'")
                index += 2
                continue
            raise FormatError(line.number, "quoting", "single quote inside a single-quoted string; double it as ''", line.raw)
        out.append(inner[index])
        index += 1
    return "".join(out)
