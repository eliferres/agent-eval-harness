"""Core of the blind two-arm evaluation harness.

Holds everything the CLI in agent_eval.py orchestrates: task fixtures, test
running in a staged temp dir, the blindness hash check, the deterministic
shuffle that builds a judging packet, scorecard parsing, and the
four-legged ship verdict.

The harness never calls a model. Arms are opaque directories produced by
whatever agent, tool, or human you point at the spec.

Stdlib only.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

# An arm may carry a metadata file naming its author. It is the one thing
# the judge must never see, so it is stripped everywhere an arm is staged.
META = "meta.json"

TASK_MANIFEST = "task.json"
SPEC = "SPEC.md"
BRIEF = "judge-brief.md"
VISIBLE = "visible-tests"
HIDDEN = "hidden-tests"

SUBMISSIONS = ("submission-1", "submission-2")

SCORECARD_TEMPLATE = """# Scorecard - {task}

Judge: <who or what judged this>

## submission-1
Score: <0-10>
Notes: <why that score>

## submission-2
Score: <0-10>
Notes: <why that score>

## verdict
Winner: <submission-1 or submission-2>
Graft reviewed: <yes or no>
Graft notes: <what the loser does better, or "nothing">
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def short(text: str, limit: int = 64) -> str:
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


# ---------- fixtures ----------


def load_task(task_dir: Path) -> dict:
    """Read and validate a task fixture. Raises ValueError at the boundary."""
    required = [task_dir / SPEC, task_dir / BRIEF, task_dir / VISIBLE, task_dir / HIDDEN]
    missing = [p.name for p in required if not p.exists()]
    if missing:
        raise ValueError(
            "Expected `%s` to be a task fixture, missing: %s" % (task_dir, ", ".join(missing))
        )
    manifest_path = task_dir / TASK_MANIFEST
    if not manifest_path.is_file():
        raise ValueError("Expected `%s` to exist (holds the shuffle seed)" % manifest_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Expected `%s` to be valid JSON: %s" % (manifest_path, exc)) from exc
    for key in ("name", "seed", "judge_floor"):
        if key not in manifest:
            raise ValueError("Expected `%s` to declare `%s`" % (manifest_path, key))
    manifest["dir"] = task_dir
    return manifest


# Directories and files that are build residue, not work product: they must
# never be staged, hashed, or counted as part of an arm.
SKIP_DIRS = ("__pycache__", ".pytest_cache", ".git")
SKIP_NAMES = (".DS_Store",)


def iter_all_files(root: Path) -> Iterator[Path]:
    """Every file under root, nothing left out. What the arm really holds."""
    for path in sorted(root.rglob("*")):
        if path.is_file():
            yield path


def iter_files(root: Path) -> Iterator[Path]:
    """The files an arm is made of: build residue left out.

    This is the staging and fingerprinting view. The contamination check
    reads the other one, because residue is exactly where a copied test
    would be parked.
    """
    for path in iter_all_files(root):
        # Relative to the arm, never the whole path: an arm that happens to
        # sit under a directory named .git walked as zero files and hashed
        # as the hash of nothing, a fingerprint no edit could move.
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.name in SKIP_NAMES or path.suffix == ".pyc":
            continue
        yield path


def stage(src: Path, dst: Path, skip_meta: bool = True) -> None:
    """Flatten-copy a fixture or arm into a staging dir, dropping identity."""
    for path in iter_files(src):
        if skip_meta and path.name == META:
            continue
        target = dst / path.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


# ---------- running tests ----------


RAN = re.compile(r"^Ran (\d+) tests?", re.M)

# Environment variables that carry the caller's working directory into the
# child. The child already runs from a scratch directory, so these were the
# last thing pointing home: an arm read one of them, walked to the checkout,
# and rewrote the hidden tests it was about to be judged by.
CWD_VARS = ("PWD", "OLDPWD")

# How long one test child may run before it is killed. Without a limit an
# arm that sleeps held the harness open until something outside ended it,
# which in CI means a job burning to the runner's limit with no verdict.
TEST_TIMEOUT = 300

# The child that runs one staged arm. `unittest` is imported before the
# staging directory reaches sys.path, which is what stops an arm shipping
# its own unittest.py from answering for the test run: discover puts the
# staging directory first, but the real module is already imported by then.
# `python -m unittest` did the two in the other order, so the arm's file won.
#
# Every test is named by its id, module.Class.method, in the progress lines
# and the failure banners alike. unittest's own description changed in
# Python 3.11 (it gained the method name), so passing it through made the
# same run print a different log on each version.
RUNNER = """
import sys
import unittest


class ById(unittest.TextTestResult):
    def getDescription(self, test):
        return test.id()


start = sys.argv[1]
suite = unittest.defaultTestLoader.discover(start, top_level_dir=start)
result = unittest.TextTestRunner(verbosity=2, resultclass=ById).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
"""


def run_tests(arm_dir: Path, tests_dir: Path, timeout: int = TEST_TIMEOUT) -> dict:
    """Run one test directory against one arm in a throwaway staging dir.

    Staging is what keeps hidden tests hidden: the arm never gains a copy,
    and the tests never live where an implementer could read them. The
    child runs from a clean scratch directory, never from the staging
    directory, so nothing the arm carries is importable before the runner
    has imported what it needs.
    """
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as scratch:
        work = Path(tmp)
        stage(arm_dir, work)
        stage(tests_dir, work)
        # PYTHONNODEBUGRANGES stops 3.11 and up drawing caret rows under a
        # traceback line, so a failing run logs the same lines on every
        # version. Both variables are ignored before Python 3.11.
        env = dict(os.environ, PYTHONSAFEPATH="1", PYTHONNODEBUGRANGES="1")
        for name in CWD_VARS:
            env.pop(name, None)
        try:
            proc = subprocess.run(
                [sys.executable, "-c", RUNNER, str(work)],
                cwd=scratch,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "ran": 0,
                "timed_out": True,
                "at": now(),
                "output": "the test run was killed after %d seconds without finishing" % timeout,
            }
    output = (proc.stdout + proc.stderr).strip()
    found = RAN.search(output)
    ran = int(found.group(1)) if found else 0
    return {
        # A clean exit status with no tests in it is not a pass. An arm that
        # ends the process before the first test runs, and a run that
        # discovered nothing to run, both left the status at 0 and the count
        # at zero, and the leg went green over code nobody tested.
        "ok": proc.returncode == 0 and ran > 0,
        "ran": ran,
        "at": now(),
        "output": "\n".join(output.splitlines()[-25:]),
    }


# unittest's own test for a module name it can import, from the loader.
MODULE_NAME = re.compile(r"[_a-z]\w*\.py$", re.I)
IMPORTS_UNITTEST = re.compile(r"^\s*(?:import\s+unittest|from\s+unittest\b)", re.M)


def looks_like_tests(path: Path) -> bool:
    """A file named for tests, or one that imports unittest.

    The rest are support modules the tests import, which discovery is
    meant to skip, so warning about them would only be noise.
    """
    return ("test" in path.name.lower()
            or IMPORTS_UNITTEST.search(path.read_text(encoding="utf-8", errors="replace"))
            is not None)


def undiscovered(tests_dir: Path) -> list[str]:
    """Test files under a test folder that discovery will never run.

    The runner finds files named test*.py, and descends only into folders
    holding an __init__.py. Anything else is skipped without a word, so a
    misnamed edge-case file leaves its tests out and the leg can go green
    on whatever trivial test is left. The rules are unittest's: the name is
    matched with fnmatch, case-sensitive on Linux and macOS.
    """
    skipped = []
    for path in iter_files(tests_dir):
        rel = path.relative_to(tests_dir)
        if path.suffix != ".py" or path.name == "__init__.py":
            continue
        folders = [tests_dir.joinpath(*rel.parts[:depth]) for depth in range(1, len(rel.parts))]
        runs = (fnmatch.fnmatch(path.name, "test*.py") and MODULE_NAME.match(path.name)
                and all((folder / "__init__.py").is_file() for folder in folders))
        if not runs and looks_like_tests(path):
            skipped.append(rel.as_posix())
    return skipped


def fixture_fingerprint(task_dir: Path) -> str:
    """Hash both of a task's test directories.

    Taken before a run and checked after it. The arm's code runs inside
    that window, and a run that edits the tests it is judged by poisons
    the fixture for every later run of every arm.
    """
    both = "|".join(arm_fingerprint(task_dir / name) for name in (VISIBLE, HIDDEN))
    return hashlib.sha256(both.encode("ascii")).hexdigest()


def check_fixture(task_dir: Path, before: str) -> None:
    """Refuse when the run changed the task's tests. Raises ValueError."""
    if fixture_fingerprint(task_dir) != before:
        raise ValueError(
            "Expected the tests in `%s` to be the tests the run started with: they were "
            "rewritten while the arm ran, so this result is worthless and the fixture needs "
            "restoring" % task_dir
        )


# ---------- blindness ----------


def content_hash(path: Path) -> str:
    """Hash a file's meaningful content.

    Trailing whitespace and blank lines are normalized away so that a
    reformatted copy of a hidden test still matches. An implementer who
    retypes a test by hand defeats this; the check catches the copy, which
    is the failure that actually happens.
    """
    text = path.read_bytes().decode("utf-8", errors="replace")
    body = "\n".join(line.rstrip() for line in text.splitlines() if line.strip())
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


# What a file with nothing but blank lines and spaces normalizes to. Every
# such file hashes alike, so comparing two of them says nothing about where
# either came from: an empty __init__.py in an arm is not a copy of an empty
# __init__.py in the hidden tests, and reading it as one accused an honest
# arm of holding the tests and left its hidden leg red for good.
EMPTY_BODY = hashlib.sha256(b"").hexdigest()


def contamination(arm_dir: Path, hidden_dir: Path) -> list[str]:
    """Hidden-test files found inside an arm. Non-empty means refuse to grade."""
    hidden = {content_hash(p): p.name
              for p in iter_files(hidden_dir) if content_hash(p) != EMPTY_BODY}
    # Every file in the arm, with nothing skipped. The staging skip list has
    # no business here: a copy parked in __pycache__, or saved with a .pyc
    # suffix, is still a copy, and skipping it let the arm clear the check
    # holding the tests.
    return [
        "%s matches hidden test %s" % (path.relative_to(arm_dir), hidden[content_hash(path)])
        for path in iter_all_files(arm_dir)
        if content_hash(path) in hidden
    ]


def blind_order(seed: str, arm_ids: list[str]) -> list[str]:
    """Shuffle arms into submission slots, reproducibly from the task seed.

    Seeding on the arm ids too means a different pair of arms gets a
    different order under the same seed, so the mapping cannot be guessed
    from one previous run.
    """
    order = sorted(arm_ids)
    random.Random("%s|%s" % (seed, "|".join(order))).shuffle(order)
    return order


# ---------- ledger ----------


def ledger_path(runs_dir: Path, task_name: str) -> Path:
    return runs_dir / task_name / "ledger.json"


# What a filed scorecard has to carry for the legs to read it.
CARD_KEYS = ("scores", "winner", "graft_reviewed", "graft_notes")


def valid_ledger(data, path: Path) -> dict:
    """Refuse a file that is JSON but not a ledger. Raises ValueError.

    The ledger is the documented audit trail, and a wrong-shaped one used
    to surface as a traceback on whichever key was read first.
    """
    if not isinstance(data, dict) or not isinstance(data.get("arms"), dict):
        raise ValueError("Expected `%s` to be a ledger holding an `arms` object" % path)
    packet = data.get("packet")
    if packet is not None:
        if not isinstance(packet, dict) or not isinstance(packet.get("order"), dict):
            raise ValueError("Expected the packet in `%s` to hold an `order` object" % path)
    card = data.get("scorecard")
    if card is not None:
        missing = ([key for key in CARD_KEYS if key not in card] if isinstance(card, dict)
                   else list(CARD_KEYS))
        if missing:
            raise ValueError(
                "Expected the scorecard in `%s` to declare %s" % (path, ", ".join(missing))
            )
    return data


def load_ledger(runs_dir: Path, task_name: str) -> dict:
    path = ledger_path(runs_dir, task_name)
    if path.is_file():
        return valid_ledger(json.loads(path.read_text(encoding="utf-8")), path)
    return {"task": task_name, "arms": {}, "packet": None, "scorecard": None}


def save_ledger(runs_dir: Path, task_name: str, ledger: dict) -> Path:
    path = ledger_path(runs_dir, task_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def arm_entry(ledger: dict, arm_dir: Path) -> dict:
    # Resolved, not as typed: a relative path recorded from one directory
    # means nothing to a command run from another.
    return ledger["arms"].setdefault(arm_dir.name, {"path": str(arm_dir.resolve())})


def arm_fingerprint(arm_dir: Path) -> str:
    """Hash an arm's contents: every file's relative path and bytes, sorted.

    Names and bytes only, never mtimes or inode data, so the same arm hashes
    the same on another machine and after a copy. This is what ties a
    recorded result to the code that produced it.

    Each field goes in as its byte length, a colon, then the bytes. A file's
    contents can hold any byte, a null included, so a separator byte would
    leave the boundary between two files guessable: delete one file, fold its
    name and bytes into another, and the hash would not move.
    """
    digest = hashlib.sha256()
    files = sorted(iter_files(arm_dir), key=lambda p: p.relative_to(arm_dir).as_posix())
    for path in files:
        for field in (path.relative_to(arm_dir).as_posix().encode("utf-8"), path.read_bytes()):
            digest.update(b"%d:" % len(field))
            digest.update(field)
    return digest.hexdigest()


def record_result(ledger: dict, arm_dir: Path, leg: str, result: dict, task_dir: Path) -> dict:
    """File one leg's result against the arm, fingerprinted as it was tested.

    Both sides of the run are fingerprinted: the arm, and the test folder
    the leg ran. A result is evidence about one arm against one set of
    tests, and either changing afterwards leaves it describing neither.
    """
    entry = arm_entry(ledger, arm_dir)
    entry["path"] = str(arm_dir.resolve())
    result["fingerprint"] = arm_fingerprint(arm_dir)
    result["tests_fingerprint"] = arm_fingerprint(task_dir / LEG_TESTS[leg])
    entry[leg] = result
    return entry


LEG_NAMES = {"visible": "visible tests", "blindness": "blindness check", "hidden": "hidden tests"}

# The test folder each leg reads. The blindness check compares the arm
# against the hidden tests, so it rests on them as much as the hidden run.
LEG_TESTS = {"visible": VISIBLE, "blindness": HIDDEN, "hidden": HIDDEN}
TEST_NAMES = {VISIBLE: "visible tests", HIDDEN: "hidden tests"}


def ran_and_passed(result) -> bool:
    """A test leg is green only when tests both ran and passed.

    A row with no count comes from a version that did not record one, or
    from a run that ended before a test did: neither is evidence.
    """
    return bool(result and result.get("ok") and result.get("ran"))


def red_detail(result) -> str:
    """Why a recorded test leg is red, in two words."""
    if result.get("timed_out"):
        return "timed out"
    if result.get("ok") and not result.get("ran"):
        return "no tests ran"
    return "failing"


def prog() -> str:
    """The name the run was invoked by, for a hint the reader can retype.

    `agent-eval` when installed, `agent_eval.py` from a clone. Installed
    there is no agent_eval.py anywhere on the machine, so naming the file
    told the reader to run something they do not have.
    """
    return os.path.basename(sys.argv[0]) or "agent-eval"


def stale_results(ledger: dict, arm_id: str, given_dir: Path, task_dir: Path) -> list[str]:
    """Recorded results that no longer describe the arm the caller named.

    `given_dir` is the directory the caller asked about. Arms are keyed by
    folder name, so without this the ledger would answer for any directory
    of that name: copy an arm elsewhere, edit the copy, ask about the copy,
    and the untouched original would clear it.

    Empty means every result was recorded against exactly the files that are
    there now, against the task's tests as they are now, the judging packet
    included. Anything else is a reason to refuse: an arm that is not the
    one that was tested, a result or a packet whose arm has changed since, a
    result whose test folder has changed since, or a record old enough to
    carry no fingerprint at all.
    """
    arm = ledger["arms"].get(arm_id, {})
    recorded = [(leg, arm[leg]) for leg in LEG_NAMES if arm.get(leg)]
    if not recorded:
        return []

    arm_dir = Path(arm["path"]) if arm.get("path") else None
    if arm_dir is None or not arm_dir.is_dir():
        return ["%s is recorded at `%s`, which is not there now - re-run the legs"
                % (arm_id, arm.get("path", ""))]
    if arm_dir.resolve() != given_dir.resolve():
        return ["%s was tested at `%s`, not at `%s` - re-run the legs against this directory"
                % (arm_id, arm_dir.resolve(), given_dir.resolve())]

    current = arm_fingerprint(arm_dir)
    tests_now = {name: arm_fingerprint(task_dir / name) for name in TEST_NAMES}
    problems = []
    for leg, result in recorded:
        tests = LEG_TESTS[leg]
        if not result.get("fingerprint"):
            problems.append(
                "%s has a %s result with no fingerprint, so it cannot be verified - re-run the legs"
                % (arm_id, LEG_NAMES[leg])
            )
        elif result["fingerprint"] != current:
            problems.append(
                "%s changed after the %s leg tested it - re-run the legs"
                % (arm_id, LEG_NAMES[leg])
            )
        elif not result.get("tests_fingerprint"):
            problems.append(
                "%s has a %s result with no fingerprint of the tests it ran, so it cannot be "
                "verified - re-run the legs" % (arm_id, LEG_NAMES[leg])
            )
        elif result["tests_fingerprint"] != tests_now[tests]:
            problems.append(
                "%s: the %s changed after the %s leg ran them - re-run the legs"
                % (arm_id, TEST_NAMES[tests], LEG_NAMES[leg])
            )

    # The judge and graft legs read a scorecard written against the packet,
    # so the packet is where their evidence lives. A scorecard filed against
    # a packet built from code the arm no longer holds is as stale as a test
    # result, and the judge never saw what is on disk now.
    packet = ledger.get("packet") or {}
    packed_ids = sorted(set((packet.get("order") or {}).values()))
    # Every arm the packet holds, not only the one named. The scorecard is a
    # comparison: replace the loser's code and the winner would still ship on
    # a judgement that no longer describes either side.
    if arm_id in packed_ids:
        for packed_id in packed_ids:
            packed = (packet.get("fingerprints") or {}).get(packed_id)
            recorded = (ledger["arms"].get(packed_id) or {}).get("path")
            where = given_dir if packed_id == arm_id else Path(recorded) if recorded else None
            if not packed:
                problems.append(
                    "%s went into the judging packet with no fingerprint, so what the judge "
                    "saw cannot be verified - re-run pack" % packed_id
                )
            elif where is None or not where.is_dir():
                problems.append(
                    "%s went into the judging packet and is not on disk now - "
                    "re-run pack and record" % packed_id
                )
            elif arm_fingerprint(where) != packed:
                problems.append(
                    "%s changed after the judging packet was built - re-run pack and record"
                    % packed_id
                )
    return problems


# ---------- packet ----------


def build_packet(task: dict, arm_dirs: list[Path], runs_dir: Path) -> dict:
    """Write the judge-facing packet and return the blinding key.

    The key is written to the ledger, one level above the packet directory,
    so handing someone the packet path hands them no identities.
    """
    if len(arm_dirs) != 2:
        raise ValueError("Expected exactly 2 arms, got %d" % len(arm_dirs))
    ids = [d.name for d in arm_dirs]
    if len(set(ids)) != 2:
        raise ValueError("Expected two differently named arms, got `%s`" % ", ".join(ids))
    by_id = {d.name: d for d in arm_dirs}

    packet = runs_dir / task["name"] / "packet"
    if packet.exists():
        shutil.rmtree(packet)
    packet.mkdir(parents=True)

    order = blind_order(str(task["seed"]), ids)
    mapping = dict(zip(SUBMISSIONS, order))
    for slot, arm_id in mapping.items():
        stage(by_id[arm_id], packet / slot)

    shutil.copyfile(task["dir"] / SPEC, packet / SPEC)
    shutil.copyfile(task["dir"] / BRIEF, packet / BRIEF)
    (packet / "scorecard.md").write_text(
        SCORECARD_TEMPLATE.format(task=task["name"]), encoding="utf-8"
    )
    return {
        "seed": task["seed"],
        "order": mapping,
        "packet": str(packet),
        # Fingerprinted as the judge sees them, so a scorecard cannot outlive
        # the code it was written about.
        "fingerprints": {arm_id: arm_fingerprint(by_id[arm_id]) for arm_id in ids},
        "at": now(),
    }


# ---------- scorecard ----------


TITLE = re.compile(r"^#\s+Scorecard\s+-\s+(.+?)\s*$", re.M)
SECTION = re.compile(r"^##\s+(.+?)\s*$", re.M)
FIELD = re.compile(r"^([A-Za-z][A-Za-z ]*):\s*(.*)$")


def _sections(text: str) -> dict:
    parts = SECTION.split(text)
    out = {}
    for name, body in zip(parts[1::2], parts[2::2]):
        fields = {}
        for line in body.splitlines():
            found = FIELD.match(line.strip())
            if found:
                fields[found.group(1).strip().lower()] = found.group(2).strip()
        out[name.strip().lower()] = fields
    return out


def _score(raw: str, where: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError(
            "Expected `%s.Score` to be an integer 0-10, got `%s`" % (where, raw)
        ) from None
    if not 0 <= value <= 10:
        raise ValueError("Expected `%s.Score` to be within 0-10, got `%d`" % (where, value))
    return value


def parse_scorecard(text: str, task_name: str) -> dict:
    """Validate a filled scorecard and return it as data. Raises ValueError."""
    title = TITLE.search(text)
    sections = _sections(text)
    for name in SUBMISSIONS + ("verdict",):
        if name not in sections:
            raise ValueError("Expected the scorecard to have a `## %s` section" % name)

    scores, notes = {}, {}
    for slot in SUBMISSIONS:
        scores[slot] = _score(sections[slot].get("score", ""), slot)
        note = sections[slot].get("notes", "")
        if not note or note.startswith("<"):
            raise ValueError("Expected `%s.Notes` to be filled in, got `%s`" % (slot, note))
        notes[slot] = note

    verdict = sections["verdict"]
    winner = verdict.get("winner", "")
    if winner not in SUBMISSIONS:
        raise ValueError(
            "Expected `verdict.Winner` to be one of %s, got `%s`" % (", ".join(SUBMISSIONS), winner)
        )
    reviewed = verdict.get("graft reviewed", "").lower()
    if reviewed not in ("yes", "no"):
        raise ValueError("Expected `verdict.Graft reviewed` to be yes or no, got `%s`" % reviewed)
    graft_notes = verdict.get("graft notes", "")
    if not graft_notes or graft_notes.startswith("<"):
        raise ValueError(
            "Expected `verdict.Graft notes` to say what the loser does better, got `%s`"
            % graft_notes
        )

    header = {}
    for line in text.split("\n##")[0].splitlines():
        found = FIELD.match(line.strip())
        if found:
            header[found.group(1).strip().lower()] = found.group(2).strip()

    card = {
        "task": title.group(1) if title else "",
        "judge": header.get("judge", ""),
        "scores": scores,
        "notes": notes,
        "winner": winner,
        "graft_reviewed": reviewed == "yes",
        "graft_notes": graft_notes,
    }
    check_card(card, task_name)
    return card


def check_card(card: dict, task_name: str) -> None:
    """The checks a filed card must pass, at record and again at ship.

    Run again at ship because a ledger can hold a card filed by a version
    that did not make them. The title has to name the task: a card is
    judged against one packet, and one written for another task would
    unblind this task's arms with someone else's verdict. The winner's
    judge leg goes green whatever the floor, so a winner scored below the
    other submission would ship the arm the judge scored lower.
    """
    if card.get("task") != task_name:
        raise ValueError(
            "Expected the scorecard to be titled `# Scorecard - %s`, got `%s`"
            % (task_name, "# Scorecard - %s" % card["task"] if card.get("task") else "no title")
        )
    judge = card.get("judge", "")
    if not judge or judge.startswith("<"):
        raise ValueError("Expected `Judge` to name who or what judged this, got `%s`" % judge)
    winner = card["winner"]
    other = next(slot for slot in SUBMISSIONS if slot != winner)
    if card["scores"][winner] < card["scores"][other]:
        raise ValueError(
            "Expected `verdict.Winner` to be scored no lower than the other submission, "
            "got %s at %d against %d" % (winner, card["scores"][winner], card["scores"][other])
        )


# ---------- the four legs ----------


def ship_legs(ledger: dict, arm_id: str, judge_floor: int) -> list[tuple]:
    """The four legs for one arm: (name, green?, detail). All green or no ship."""
    arm = ledger["arms"].get(arm_id, {})
    command = prog()
    legs = []

    visible = arm.get("visible")
    visible_ok = ran_and_passed(visible)
    legs.append(
        ("visible tests", visible_ok,
         "%d passed" % visible["ran"] if visible_ok
         else red_detail(visible) if visible
         else "never run (%s check)" % command)
    )

    hidden = arm.get("hidden")
    blind = arm.get("blindness")
    hidden_ok = ran_and_passed(hidden) and bool(blind and blind["clean"])
    legs.append(
        ("hidden tests", hidden_ok,
         "%d passed, blindness verified" % hidden["ran"] if hidden_ok
         else "arm contains hidden tests" if blind and not blind["clean"]
         else red_detail(hidden) if hidden
         else "never run (%s grade)" % command)
    )

    card = ledger.get("scorecard")
    packet = ledger.get("packet")
    if not card or not packet:
        legs.append(("blind judge", False,
                     "no scorecard filed (%s pack, then record)" % command))
    else:
        slot = next((s for s, a in packet["order"].items() if a == arm_id), None)
        score = card["scores"].get(slot, 0)
        won = card["winner"] == slot
        legs.append(
            ("blind judge", won or score >= judge_floor,
             "%s as %s, score %d/10 (floor %d)" % ("picked" if won else "not picked", slot, score,
                                                   judge_floor))
        )

    if not card:
        legs.append(("graft review", False, "not recorded"))
    else:
        note = card["graft_notes"]
        legs.append(
            ("graft review", card["graft_reviewed"],
             "recorded: %s" % short(note) if card["graft_reviewed"] else "not reviewed")
        )
    return legs
