"""``python -m evalloop check <path>`` -- the one-shot M1 command.

A thin argument layer over :func:`evalloop.run.check`; all the work is there. The three exit codes
are the driver's honest outcomes (``AGENT.md`` / ``USER_EXPERIENCE.md``): 0 clean, 1 a problem
found, 2 nothing could be decided.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from evalloop.run import RunResult, check


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evalloop", description="Evaluate a repository, honestly.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("check", help="run the whole loop on a path and write summary.md")
    run.add_argument("path", help="the file or repository to evaluate")
    run.add_argument("--store", required=True, help="directory for the metric store and summary.md")
    run.add_argument("--out", default=None, help="where to write summary.md (default: <store>/summary.md)")
    run.add_argument("--seed", type=int, default=0, help="seed for a deterministic run id and sandbox")
    run.add_argument(
        "--no-llm",
        action="store_true",
        default=True,
        help="grade on harvested oracles only, with zero egress (the M1 default and guarantee)",
    )
    run.add_argument("--wall-seconds", type=float, default=30.0, help="per-grading wall-clock cap")
    return parser


def _print_result(result: RunResult, stream: object) -> None:
    write = stream.write  # type: ignore[attr-defined]
    write(f"EvalLoop: {result.outcome.value.upper()} (run {result.run_id})\n")
    write(f"  report: {result.summary_path}\n")
    if result.permission_requests:
        write("  permission requests (a missing tool is a request, not a skip):\n")
        for line in result.permission_requests:
            write(f"    - {line}\n")
    for line in result.skipped:
        write(f"  skipped: {line}\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "check":
        result = check(
            args.path,
            store_dir=args.store,
            out_path=args.out,
            no_llm=args.no_llm,
            seed=args.seed,
            wall_seconds=args.wall_seconds,
        )
        _print_result(result, sys.stdout)
        return result.exit_code
    parser.error("no command")  # unreachable: the subparser is required


if __name__ == "__main__":
    raise SystemExit(main())
