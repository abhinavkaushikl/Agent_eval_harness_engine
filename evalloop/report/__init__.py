"""Rendering a run for a human (``USER_EXPERIENCE.md`` §3.4).

M1 has one output here: ``summary.render_summary`` builds the ``summary.md`` for one run. The live
dashboard, the local API and trend lines are later milestones.
"""

from __future__ import annotations

from evalloop.report.summary import Session, render_summary

__all__ = ["Session", "render_summary"]
