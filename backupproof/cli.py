"""Command line: check, add (job), jobs, run (all jobs), history, gui. Exit code 1 when a backup has problems."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import __version__, report
from .verify import DEFAULT_IGNORE, verify


def summarize(result) -> None:
    print(result.headline())
    for kind, path, detail in report.rows(result)[:25]:
        print(f"  {kind:<22} {path}  {detail}")
    more = len(report.rows(result)) - 25
    if more > 0:
        print(f"  ... and {more} more (use --html for the full list)")


def run_one(source: str, backup: str, args) -> bool:
    result = verify(source, backup, mode=args.mode, sample_percent=args.sample, ignore=DEFAULT_IGNORE + tuple(args.ignore),
                    progress=(lambda d, t, p: print(f"  verifying {d}/{t}", file=sys.stderr)) if args.verbose else None)
    summarize(result)
    report.record(result)
    if args.html:
        print(f"Report: {report.write_html(result, Path(args.html))}")
    if args.csv:
        print(f"CSV: {report.write_csv(result, Path(args.csv))}")
    return result.ok


def cmd_check(args) -> int:
    return 0 if run_one(args.source, args.backup, args) else 1


def cmd_add(args) -> int:
    jobs = report.load_jobs()
    jobs.append({"name": args.name or Path(args.source).name, "source": str(Path(args.source).resolve()),
                 "backup": str(Path(args.backup).resolve())})
    report.save_jobs(jobs)
    print(f"Saved job {jobs[-1]['name']!r}.")
    return 0


def cmd_jobs(args) -> int:
    for job in report.load_jobs():
        print(f"{job['name']}: {job['source']}  ->  {job['backup']}")
    return 0


def cmd_run(args) -> int:
    ok = True
    for job in report.load_jobs():
        print(f"\n== {job['name']}")
        try:
            ok = run_one(job["source"], job["backup"], args) and ok
        except FileNotFoundError as exc:
            print(f"  {exc}")
            ok = False
    return 0 if ok else 1


def cmd_history(args) -> int:
    for line in report.history():
        print(f"{line['time']}  {'OK ' if line['ok'] else 'BAD'}  {line['mode']:<6} {line['summary']}  ({line['source']})")
    return 0


def cmd_gui(args) -> int:
    from .gui import main as gui_main
    return gui_main()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="backupproof", description="Prove your backup matches the originals.")
    parser.add_argument("--version", action="version", version=f"BackupProof {__version__}")
    sub = parser.add_subparsers(dest="command")

    def options(p) -> None:
        p.add_argument("--mode", choices=["quick", "sample", "deep"], default="quick")
        p.add_argument("--sample", type=float, default=5.0, help="percent of files to read in sample mode")
        p.add_argument("--ignore", action="append", default=[], help="extra name pattern to skip, e.g. *.bak")
        p.add_argument("--html")
        p.add_argument("--csv")
        p.add_argument("-v", "--verbose", action="store_true")

    p = sub.add_parser("check", help="compare SOURCE with BACKUP")
    p.add_argument("source")
    p.add_argument("backup")
    options(p)
    p.set_defaults(func=cmd_check)
    p = sub.add_parser("add", help="save a source/backup pair as a job")
    p.add_argument("source")
    p.add_argument("backup")
    p.add_argument("--name")
    p.set_defaults(func=cmd_add)
    sub.add_parser("jobs", help="list saved jobs").set_defaults(func=cmd_jobs)
    p = sub.add_parser("run", help="check every saved job")
    options(p)
    p.set_defaults(func=cmd_run)
    sub.add_parser("history", help="recent results").set_defaults(func=cmd_history)
    sub.add_parser("gui", help="open the window").set_defaults(func=cmd_gui)
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        return cmd_gui(args)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
