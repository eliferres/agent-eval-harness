"""Replays demo/transcript.json and checks demo/terminal.svg against it.

The README shows a terminal session. This runs that session for real, in a
throwaway copy of the repo, and refuses anything that does not match:
every command's output and exit code must be what the transcript claims,
and every row drawn in the picture must be a row that run produced.

Set UPDATE_DEMO_TRANSCRIPT=1 to rewrite the transcript from the real run.
The JSON is never edited by hand.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TRANSCRIPT = REPO / "demo" / "transcript.json"
PICTURE = REPO / "demo" / "terminal.svg"
SVG_NS = {"svg": "http://www.w3.org/2000/svg"}
ELLIPSIS = "…"

# Directories a fresh clone does not carry, so the copy does not either.
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "runs", "build", "dist"}

# The harness runs tests in a staging dir under the system temp dir, and the
# path shows up in a failing test's traceback.
STAGING = re.compile(r"(/private)?(/var/folders/[^\s\"]+?|/tmp)/tmp[A-Za-z0-9_]+")
DURATION = re.compile(r"^(Ran \d+ tests? in )[0-9.]+s$", re.M)

# Python 3.11 and up underline the failing expression under the source line
# of a traceback frame; older versions print no such row. The underline is
# indented, is made only of spaces, tildes and carets, and carries at least
# one caret.
TRACEBACK_HEAD = "Traceback (most recent call last):"
UNDERLINE = re.compile(r"^ +[ ~^]*\^[ ~^]*$")


def drop_underlines(text: str) -> str:
    """Remove the caret rows a 3.11+ traceback draws, and nothing else.

    A row is dropped only inside a traceback block, only directly under an
    indented row of that block, and only if it looks like an underline. A
    line of spaces and tildes the command really printed is output, not
    decoration, and is kept.
    """
    kept, in_traceback, under_frame = [], False, False
    for line in text.splitlines():
        if line.strip() == TRACEBACK_HEAD:
            in_traceback = True
        elif in_traceback and line.strip() and not line.startswith(" "):
            in_traceback = False  # the exception line closes the block
        if in_traceback and under_frame and UNDERLINE.match(line):
            continue
        kept.append(line)
        under_frame = bool(line.strip()) and line.startswith(" ")
    return "\n".join(kept)


def normalize(text: str, copy_root: Path) -> str:
    """Strip out everything that is about this machine rather than the run."""
    for root in (str(copy_root.resolve()), str(copy_root)):
        text = text.replace(root, "/path/to/checkout")
    text = STAGING.sub("/path/to/staging", text)
    text = DURATION.sub(r"\g<1>0.000s", text)
    return drop_underlines(text).strip()


def run_transcript(copy_root: Path) -> list:
    entries = json.loads(TRANSCRIPT.read_text(encoding="utf-8"))
    actual = []
    for entry in entries:
        proc = subprocess.run(
            ["bash", "-c", entry["cmd"]], cwd=str(copy_root),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        actual.append({"cmd": entry["cmd"],
                       "out": normalize(proc.stdout, copy_root),
                       "status": proc.returncode})
    return entries, actual


def picture_rows() -> list:
    """The drawn rows of the picture, in order, as (kind, text).

    kind is "cmd" for a prompt row, "cmd-cont" for a wrapped continuation,
    and "out" for anything else. The window chrome is the one text element
    that carries its own font-size, so it is the one that is not a row.
    """
    root = ET.parse(PICTURE).getroot()
    rows = []
    for element in root.findall("svg:text", SVG_NS):
        if element.get("font-size") is not None:
            continue
        tspans = element.findall("svg:tspan", SVG_NS)
        if tspans:
            rows.append(("cmd", tspans[-1].text or ""))
            continue
        text = element.text or ""
        if element.get("class") == "cmd" and text.startswith("    "):
            rows.append(("cmd-cont", text[4:]))
        else:
            rows.append(("out", text))
    return rows


def rejoin(chunks: list) -> str:
    """Undo the wrap: continuation rows end in ` \\` and rejoin on one space."""
    return " ".join(c[:-2] if c.endswith(" \\") else c for c in chunks)


def shows(drawn: str, real: str) -> bool:
    """True if the drawn row is the real line, or it end-trimmed with one ellipsis."""
    if drawn == real:
        return True
    head = drawn[: -len(ELLIPSIS)]
    return (drawn.endswith(ELLIPSIS) and drawn.count(ELLIPSIS) == 1
            and len(head) < len(real) and real.startswith(head))


class NormalizeTest(unittest.TestCase):
    """The normalizer may only hide traceback decoration, never real output."""

    def test_a_printed_line_of_spaces_and_tildes_is_kept(self):
        printed = "grade: arm-b hidden tests FAIL\n    ~~~~~~~~\nRan 5 tests\n"
        self.assertIn("    ~~~~~~~~", normalize(printed, REPO))

    def test_a_3_11_underline_in_a_traceback_is_dropped(self):
        failure = ("Traceback (most recent call last):\n"
                   '  File "/path/to/staging/test_wrap_edges.py", line 15, in test_x\n'
                   "    self.assertEqual(wrap(\"ab\", 5), [\"ab\"])\n"
                   "    ~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^\n"
                   "AssertionError: Lists differ\n")
        self.assertNotIn("^", normalize(failure, REPO))


class TranscriptTest(unittest.TestCase):
    def test_every_entry_replays_to_the_recorded_output_and_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "checkout"
            shutil.copytree(REPO, copy,
                            ignore=shutil.ignore_patterns(*SKIP_DIRS, "*.pyc"))
            recorded, actual = run_transcript(copy)

        if os.environ.get("UPDATE_DEMO_TRANSCRIPT") == "1":
            TRANSCRIPT.write_text(json.dumps(actual, indent=2) + "\n", encoding="utf-8")
            self.skipTest("rewrote demo/transcript.json from the real run")

        self.assertEqual(len(recorded), len(actual))
        for was, is_now in zip(recorded, actual):
            with self.subTest(was["cmd"]):
                self.assertEqual(was["out"], is_now["out"])
                self.assertEqual(was["status"], is_now["status"])


class PictureTest(unittest.TestCase):
    """Every row of demo/terminal.svg, walked against the transcript in order.

    The picture may show fewer entries than the transcript holds, but it may
    stop only where one command's output ends and the next begins, and no row
    it draws may be one the run never printed.
    """

    def test_the_picture_draws_the_transcript_and_nothing_else(self):
        entries = json.loads(TRANSCRIPT.read_text(encoding="utf-8"))
        rows = picture_rows()
        self.assertTrue(rows, "the picture has no rows")

        at = 0
        for entry in entries:
            if at == len(rows):
                break  # the picture stopped at a command boundary, which is allowed
            kind, text = rows[at]
            self.assertEqual(kind, "cmd", "row %d starts an entry, so it must be a command row" % (at + 1))
            chunks, at = [text], at + 1
            while at < len(rows) and rows[at][0] == "cmd-cont":
                chunks.append(rows[at][1])
                at += 1
            self.assertEqual(rejoin(chunks), entry["cmd"],
                             "rows %d-%d do not rejoin into the command that was run" % (at - len(chunks) + 1, at))

            for line in [l for l in entry["out"].splitlines() if l.strip()]:
                self.assertLess(at, len(rows),
                                "the picture stops mid-command, before the output line %r" % line)
                drawn = rows[at][1]
                self.assertTrue(shows(drawn, line),
                                "row %d draws %r, but the run printed %r there" % (at + 1, drawn, line))
                at += 1

        self.assertEqual(at, len(rows),
                         "rows %d onward are drawn but the transcript never produced them" % (at + 1))


if __name__ == "__main__":
    unittest.main()
