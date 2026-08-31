#!/usr/bin/env python3
"""Blind two-arm evaluation harness for AI agent work.

Six subcommands, in the order you run them:

    init    scaffold a task fixture
    check   run the visible tests for one arm
    grade   blindness check, then the hidden tests
    pack    build the blind judging packet
    record  file a judge's scorecard and unblind it
    ship    print the four legs and refuse while any is red

Everything is written to runs/<task>/ledger.json, which is the audit
trail: what was run, when, with which seed, and how the shuffle mapped.

Stdlib only. Exit 0 on green, 1 on a red or refused verdict, 2 on bad input.

Usage:
    python eval.py <command> --help
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

import harness

GREEN, RED = "[green]", "[ RED ]"

SCAFFOLD = {
    harness.SPEC: """# Task: {name}

What to build, precisely enough that two independent attempts are
comparable. State the entry point, the signature, and the rules.

## Rules

1.
2.

## Out of scope
""",
    harness.BRIEF: """# Judge brief: {name}

Written BEFORE any arm runs, so the bar is not bent to fit the results.

**What good looks like here.** ...

**Score 0-10.** 8+ means it would pass review unchanged. Below 5 means
a rewrite is cheaper than a fix.

**Weigh, in order:** correctness against the spec, readability, error
handling at the boundary, restraint (no abstraction the task did not ask
for).

**Ignore:** formatting preferences, and any guess about who wrote what.
""",
    "visible-tests/test_visible.py": '''"""Tests the implementer may run. Keep them representative, not exhaustive."""

import unittest


class VisibleTest(unittest.TestCase):
    def test_placeholder(self):
        self.fail("write the visible tests for this task")
''',
    "hidden-tests/test_hidden.py": '''"""Tests the implementer never sees. Put the edges here."""

import unittest


class HiddenTest(unittest.TestCase):
    def test_placeholder(self):
        self.fail("write the hidden edge tests for this task")
''',
}


def cmd_init(args) -> int:
    task_dir = Path(args.task)
    if task_dir.exists():
        print("init: %s already exists" % task_dir)
        return 2
    name = args.name or task_dir.name
    for rel, body in SCAFFOLD.items():
        path = task_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body.format(name=name), encoding="utf-8")
    manifest = '{\n  "name": "%s",\n  "seed": "%s",\n  "judge_floor": %d\n}\n' % (
        name, secrets.token_hex(8), args.floor
    )
    (task_dir / harness.TASK_MANIFEST).write_text(manifest, encoding="utf-8")
    print("init: scaffolded %s (fill SPEC.md and the two test dirs before running an arm)" % task_dir)
    return 0


def cmd_check(args) -> int:
    task = harness.load_task(Path(args.task))
    arm_dir = Path(args.arm)
    result = harness.run_tests(arm_dir, task["dir"] / harness.VISIBLE)
    ledger = harness.load_ledger(Path(args.runs), task["name"])
    harness.arm_entry(ledger, arm_dir)["visible"] = result
    harness.save_ledger(Path(args.runs), task["name"], ledger)
    print(result["output"])
    print("check: %s visible tests %s (%d ran)"
          % (arm_dir.name, "PASS" if result["ok"] else "FAIL", result["ran"]))
    return 0 if result["ok"] else 1


def cmd_grade(args) -> int:
    task = harness.load_task(Path(args.task))
    arm_dir = Path(args.arm)
    hidden_dir = task["dir"] / harness.HIDDEN
    leaks = harness.contamination(arm_dir, hidden_dir)

    ledger = harness.load_ledger(Path(args.runs), task["name"])
    entry = harness.arm_entry(ledger, arm_dir)
    entry["blindness"] = {"clean": not leaks, "leaks": leaks, "at": harness.now()}
    if leaks:
        entry.pop("hidden", None)
        harness.save_ledger(Path(args.runs), task["name"], ledger)
        for leak in leaks:
            print("grade: %s" % leak)
        print("grade: REFUSED - %s holds a copy of the hidden tests" % arm_dir.name)
        return 1

    result = harness.run_tests(arm_dir, hidden_dir)
    entry["hidden"] = result
    harness.save_ledger(Path(args.runs), task["name"], ledger)
    print(result["output"])
    print("grade: %s hidden tests %s (%d ran, blindness verified)"
          % (arm_dir.name, "PASS" if result["ok"] else "FAIL", result["ran"]))
    return 0 if result["ok"] else 1


def cmd_pack(args) -> int:
    task = harness.load_task(Path(args.task))
    arms = [Path(a) for a in args.arms]
    key = harness.build_packet(task, arms, Path(args.runs))
    ledger = harness.load_ledger(Path(args.runs), task["name"])
    for arm in arms:
        harness.arm_entry(ledger, arm)
    ledger["packet"] = key
    ledger["scorecard"] = None  # a new packet invalidates the card written against the old one
    harness.save_ledger(Path(args.runs), task["name"], ledger)
    print("pack: %s" % key["packet"])
    print("pack: give the judge that directory and nothing above it; "
          "the unblinding key is in %s" % harness.ledger_path(Path(args.runs), task["name"]))
    return 0


def cmd_record(args) -> int:
    task = harness.load_task(Path(args.task))
    ledger = harness.load_ledger(Path(args.runs), task["name"])
    if not ledger.get("packet"):
        print("record: no packet for %s - run pack first" % task["name"])
        return 2
    card = harness.parse_scorecard(Path(args.scorecard).read_text(encoding="utf-8"))
    ledger["scorecard"] = card
    harness.save_ledger(Path(args.runs), task["name"], ledger)

    order = ledger["packet"]["order"]
    for slot in harness.SUBMISSIONS:
        print("record: %s = %s, score %d/10" % (slot, order[slot], card["scores"][slot]))
    print("record: winner %s unblinds to %s" % (card["winner"], order[card["winner"]]))
    print("record: graft reviewed %s - %s"
          % ("yes" if card["graft_reviewed"] else "NO", harness.short(card["graft_notes"])))
    return 0


def cmd_ship(args) -> int:
    task = harness.load_task(Path(args.task))
    arm_id = Path(args.arm).name
    ledger = harness.load_ledger(Path(args.runs), task["name"])
    floor = args.floor if args.floor is not None else int(task["judge_floor"])
    legs = harness.ship_legs(ledger, arm_id, floor)

    print("ship: %s / %s" % (task["name"], arm_id))
    for name, green, detail in legs:
        print("  %s %-14s %s" % (GREEN if green else RED, name, detail))
    if all(green for _, green, _ in legs):
        print("SHIP")
        return 0
    print("NO SHIP - %d of 4 legs green" % sum(1 for _, green, _ in legs if green))
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eval.py", description=__doc__.splitlines()[0])
    parser.add_argument("--runs", default="runs", help="where ledgers and packets are written")
    subs = parser.add_subparsers(dest="command", required=True)

    init = subs.add_parser("init", help="scaffold a task fixture")
    init.add_argument("task")
    init.add_argument("--name", help="task name (default: the directory name)")
    init.add_argument("--floor", type=int, default=8, help="judge score floor for shipping")
    init.set_defaults(func=cmd_init)

    for name, func, help_text in (
        ("check", cmd_check, "run the visible tests for one arm"),
        ("grade", cmd_grade, "blindness check, then the hidden tests"),
    ):
        sub = subs.add_parser(name, help=help_text)
        sub.add_argument("task")
        sub.add_argument("arm")
        sub.set_defaults(func=func)

    pack = subs.add_parser("pack", help="build the blind judging packet")
    pack.add_argument("task")
    pack.add_argument("arms", nargs=2)
    pack.set_defaults(func=cmd_pack)

    record = subs.add_parser("record", help="file a filled scorecard and unblind it")
    record.add_argument("task")
    record.add_argument("scorecard")
    record.set_defaults(func=cmd_record)

    ship = subs.add_parser("ship", help="print the four legs and the verdict")
    ship.add_argument("task")
    ship.add_argument("arm")
    ship.add_argument("--floor", type=int, help="override the task's judge score floor")
    ship.set_defaults(func=cmd_ship)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, FileNotFoundError) as exc:
        print("%s: %s" % (args.command, exc))
        return 2


if __name__ == "__main__":
    sys.exit(main())
