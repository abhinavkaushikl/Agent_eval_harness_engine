# EvalLoop

An autonomous evaluation harness. It watches what you build, works out the situation,
and picks evaluation techniques from a codified methodology (`knowledge rules/`).

**Current phase:** Milestone 0, "The Brain" (technique registry + planner only).

Requires Python **3.10+** (decision `EL-012`); 3.12 is what the dev venv below uses.

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/python -m pytest
.venv/bin/python -m mypy --strict evalloop/
```

`EVALLOOP_CORPUS` overrides the corpus directory; it defaults to the in-repo `knowledge rules/`.
