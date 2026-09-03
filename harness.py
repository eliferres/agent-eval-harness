"""Core of the blind two-arm evaluation harness.

Holds everything the CLI in eval.py orchestrates: task fixtures, test
running in a staged temp dir, the blindness hash check, the deterministic
shuffle that builds a judging packet, scorecard parsing, and the
four-legged ship verdict.

The harness never calls a model. Arms are opaque directories produced by
whatever agent, tool, or human you point at the spec.

Stdlib only.
"""

from __future__ import annotations

import hashlib
import json
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


def iter_files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.name != ".DS_Store":
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


def run_tests(arm_dir: Path, tests_dir: Path) -> dict:
    """Run one test directory against one arm in a throwaway staging dir.

    Staging is what keeps hidden tests hidden: the arm never gains a copy,
    and the tests never live where an implementer could read them.
    """
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        stage(arm_dir, work)
        stage(tests_dir, work)
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", str(work), "-t", str(work), "-v"],
            cwd=str(work),
            capture_output=True,
            text=True,
        )
    output = (proc.stdout + proc.stderr).strip()
    found = RAN.search(output)
    return {
        "ok": proc.returncode == 0,
        "ran": int(found.group(1)) if found else 0,
        "at": now(),
        "output": "\n".join(output.splitlines()[-25:]),
    }


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


def contamination(arm_dir: Path, hidden_dir: Path) -> list[str]:
    """Hidden-test files found inside an arm. Non-empty means refuse to grade."""
    hidden = {content_hash(p): p.name for p in iter_files(hidden_dir)}
    return [
        "%s matches hidden test %s" % (path.relative_to(arm_dir), hidden[content_hash(path)])
        for path in iter_files(arm_dir)
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


def load_ledger(runs_dir: Path, task_name: str) -> dict:
    path = ledger_path(runs_dir, task_name)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"task": task_name, "arms": {}, "packet": None, "scorecard": None}


def save_ledger(runs_dir: Path, task_name: str, ledger: dict) -> Path:
    path = ledger_path(runs_dir, task_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def arm_entry(ledger: dict, arm_dir: Path) -> dict:
    return ledger["arms"].setdefault(arm_dir.name, {"path": str(arm_dir)})


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
    return {"seed": task["seed"], "order": mapping, "packet": str(packet), "at": now()}


# ---------- scorecard ----------


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


def parse_scorecard(text: str) -> dict:
    """Validate a filled scorecard and return it as data. Raises ValueError."""
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

    return {
        "judge": header.get("judge", ""),
        "scores": scores,
        "notes": notes,
        "winner": winner,
        "graft_reviewed": reviewed == "yes",
        "graft_notes": graft_notes,
    }


# ---------- the four legs ----------


def ship_legs(ledger: dict, arm_id: str, judge_floor: int) -> list[tuple]:
    """The four legs for one arm: (name, green?, detail). All green or no ship."""
    arm = ledger["arms"].get(arm_id, {})
    legs = []

    visible = arm.get("visible")
    legs.append(
        ("visible tests", bool(visible and visible["ok"]),
         "%d passed" % visible["ran"] if visible and visible["ok"]
         else "failing" if visible else "never run (eval.py check)")
    )

    hidden = arm.get("hidden")
    blind = arm.get("blindness")
    hidden_ok = bool(hidden and hidden["ok"] and blind and blind["clean"])
    legs.append(
        ("hidden tests", hidden_ok,
         "%d passed, blindness verified" % hidden["ran"] if hidden_ok
         else "arm contains hidden tests" if blind and not blind["clean"]
         else "failing" if hidden else "never run (eval.py grade)")
    )

    card = ledger.get("scorecard")
    packet = ledger.get("packet")
    if not card or not packet:
        legs.append(("blind judge", False, "no scorecard filed (eval.py pack, then record)"))
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
