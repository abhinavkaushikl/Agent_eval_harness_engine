"""``python -m evalloop check <path>`` -- the one-shot M1 command.

A thin argument layer over :func:`evalloop.run.check`; all the work is there. The three exit codes
are the driver's honest outcomes (``AGENT.md`` / ``USER_EXPERIENCE.md``): 0 clean, 1 a problem
found, 2 nothing could be decided.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from evalloop.connect.scan import inspect_sqlite, render_scan, scan
from evalloop.run import RunResult, check
from evalloop.session import Session


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

    conn = sub.add_parser("connect", help="discover the databases and vector stores a repo talks to")
    conn.add_argument("path", help="the repository to scan (nothing is opened)")

    probe = sub.add_parser("probe", help="open a local SQLite file read-only and describe it")
    probe.add_argument("--sqlite", required=True, help="path to a local SQLite file")
    probe.add_argument("--endpoint", default=None, help="endpoint name for the grant and audit (default: sqlite:///<name>)")

    start = sub.add_parser("start", help="watch a repo and evaluate on every change, with a live dashboard")
    start.add_argument("path", help="the repository to watch")
    start.add_argument("--store", required=True, help="directory for the metric store")
    start.add_argument("--interval", type=float, default=2.0, help="seconds between change checks")
    start.add_argument("--port", type=int, default=7420, help="port for the live dashboard")
    start.add_argument("--no-serve", action="store_true", help="do not start the dashboard server")
    start.add_argument("--once", action="store_true", help="run a single tick and exit (no loop)")
    start.add_argument("--bot", action="store_true", help="also open the floating desktop bot (on-screen, not a browser tab)")
    start.add_argument(
        "--author",
        action="store_true",
        help="when a file has no test, WRITE one with the configured model (needs GROQ_API_KEY and prices; sends code off this machine)",
    )
    start.add_argument("--budget", default="1.00", help="spend cap in USD for authored tests this session")

    bot = sub.add_parser("bot", help="open the floating desktop bot, connected to a running `start` session")
    bot.add_argument("--host", default="127.0.0.1", help="host the session dashboard is served on")
    bot.add_argument("--port", type=int, default=7420, help="port the session dashboard is served on")
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
    if args.command == "connect":
        report = scan(args.path)
        sys.stdout.write(render_scan(report))
        # 0 = something found to consider, 2 = nothing referenced (nothing to decide).
        return 0 if report.findings else 2
    if args.command == "probe":
        inspection = inspect_sqlite(args.sqlite, endpoint=args.endpoint)
        sys.stdout.write(f"EvalLoop probe: {inspection.endpoint}\n")
        sys.stdout.write(f"  {inspection.probe.detail}\n")
        sys.stdout.write(f"  read-only: {inspection.read_only}\n")
        for table in inspection.schema.tables:
            cols = ", ".join(f"{c.name}:{c.type}" for c in table.columns)
            sys.stdout.write(f"  table {table.name} ({cols})\n")
        # 0 = reachable and read-only (validated), 1 = reachable but not read-only, 2 = unreachable.
        if not inspection.probe.reachable:
            return 2
        return 0 if inspection.read_only else 1
    if args.command == "start":
        author = None
        if args.author:
            from decimal import Decimal

            from evalloop.capability.grok import AuthoringUnavailable, build_groq_router
            from evalloop.capability.llm import Clearance
            from evalloop.run import Author

            try:
                author = Author(
                    router=build_groq_router(budget_usd=Decimal(args.budget)),
                    clearance=Clearance(
                        granted_by="evalloop start --author",
                        reason="the operator asked for tests to be written when none exist",
                    ),
                )
                sys.stdout.write("  authoring: ON — a file with no test gets one written for it\n")
            except AuthoringUnavailable as exc:
                sys.stdout.write(f"  authoring: OFF — {exc}\n")
        session = Session(args.path, store_dir=args.store, author=author)
        server = None if args.no_serve else session.serve(port=args.port)
        if server is not None:
            sys.stdout.write(f"EvalLoop watching {args.path}\n  dashboard: http://127.0.0.1:{args.port}/  (Ctrl-C to stop)\n")
        if args.once:
            card = session.tick()
            sys.stdout.write(f"  tick: {'no change' if card is None else card.outcome.upper()}\n")
            return 0
        if args.bot:
            # Tk owns the main thread; the watcher loop runs beside it and stops when the bot closes.
            import threading as _threading

            from evalloop.session.overlay import run_overlay

            watcher = _threading.Thread(target=session.run_forever, kwargs={"interval": args.interval}, daemon=True)
            watcher.start()
            sys.stdout.write("  bot: floating on-screen companion opened (right-click or Esc to close)\n")
            run_overlay(port=args.port, poll=max(1.0, args.interval))
            session.stop()
            return 0
        try:
            session.run_forever(interval=args.interval)
        except KeyboardInterrupt:
            session.stop()
            sys.stdout.write("\nstopped.\n")
        return 0
    if args.command == "bot":
        from evalloop.session.overlay import run_overlay

        run_overlay(host=args.host, port=args.port)
        return 0
    parser.error("no command")  # unreachable: the subparser is required


if __name__ == "__main__":
    raise SystemExit(main())
