"""Data access for support-copilot. Real enough to be discovered; not run by EvalLoop."""

from __future__ import annotations

import os

from sqlalchemy import create_engine  # type: ignore[import-not-found]


def engine():  # noqa: ANN201 - sample app, not type-checked by EvalLoop
    """Open the order database named by DATABASE_URL."""
    return create_engine(os.environ["DATABASE_URL"], future=True)
