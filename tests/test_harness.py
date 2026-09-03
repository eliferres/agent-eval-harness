"""Tests for the harness core.

Every case builds a real task fixture and real arms on disk in a temp
directory and runs the real functions on them. No mocks, no network.
"""

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import harness  # noqa: E402

GOOD_ARM = "def answer():\n    return 42\n"
BAD_ARM = "def answer():\n    return 41\n"

VISIBLE_TEST = """import unittest
from solution import answer


class T(unittest.TestCase):
    def test_answer_is_a_number(self):
        self.assertIsInstance(answer(), int)
"""

HIDDEN_TEST = """import unittest
from solution import answer


class T(unittest.TestCase):
    def test_answer_is_42(self):
        self.assertEqual(answer(), 42)
"""

FILLED_CARD = """# Scorecard - t

Judge: a human

## submission-1
Score: 4
Notes: misses an edge

## submission-2
Score: 9
Notes: clean

## verdict
Winner: submission-2
Graft reviewed: yes
Graft notes: nothing worth taking
"""


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def build_task(root: Path, name: str = "t", seed: str = "seed-1") -> dict:
    write(root / harness.SPEC, "# Task\n")
    write(root / harness.BRIEF, "# Brief\n")
    write(root / harness.VISIBLE / "test_v.py", VISIBLE_TEST)
    write(root / harness.HIDDEN / "test_h.py", HIDDEN_TEST)
    write(root / harness.TASK_MANIFEST,
          '{"name": "%s", "seed": "%s", "judge_floor": 8}\n' % (name, seed))
    return harness.load_task(root)


def build_arm(root: Path, source: str = GOOD_ARM) -> Path:
    write(root / "solution.py", source)
    write(root / harness.META, '{"arm": "%s"}\n' % root.name)
    return root


def ledger_with(**over) -> dict:
    green = {
        "visible": {"ok": True, "ran": 3},
        "hidden": {"ok": True, "ran": 2},
        "blindness": {"clean": True, "leaks": []},
    }
    green.update(over.pop("arm", {}))
    ledger = {
        "task": "t",
        "arms": {"arm-a": green},
        "packet": {"order": {"submission-1": "arm-b", "submission-2": "arm-a"}},
        "scorecard": {"scores": {"submission-1": 4, "submission-2": 9},
                      "winner": "submission-2", "graft_reviewed": True,
                      "graft_notes": "nothing worth taking"},
    }
    ledger.update(over)
    return ledger


class HarnessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.task = build_task(self.root / "task")

    def test_clean_arm_is_not_contaminated(self):
        arm = build_arm(self.root / "arm-a")
        self.assertEqual(harness.contamination(arm, self.task["dir"] / harness.HIDDEN), [])

    def test_copied_hidden_test_is_caught(self):
        arm = build_arm(self.root / "arm-a")
        write(arm / "notes" / "borrowed.py", HIDDEN_TEST)
        leaks = harness.contamination(arm, self.task["dir"] / harness.HIDDEN)
        self.assertTrue(any("test_h.py" in leak for leak in leaks), leaks)

    def test_reformatted_hidden_test_is_still_caught(self):
        # Copy-then-reformat is the realistic contamination, so the hash
        # normalizes blank lines and trailing whitespace away.
        arm = build_arm(self.root / "arm-a")
        reformatted = "\n\n".join(line + "   " for line in HIDDEN_TEST.splitlines())
        write(arm / "borrowed.py", reformatted)
        self.assertTrue(harness.contamination(arm, self.task["dir"] / harness.HIDDEN))

    def test_shuffle_is_deterministic_from_the_seed(self):
        first = harness.blind_order("seed-1", ["arm-a", "arm-b"])
        self.assertEqual(first, harness.blind_order("seed-1", ["arm-b", "arm-a"]))

    def test_shuffle_varies_across_seeds(self):
        orders = {tuple(harness.blind_order("s%d" % i, ["arm-a", "arm-b"])) for i in range(20)}
        self.assertEqual(len(orders), 2, orders)

    def test_tests_run_against_the_arm_and_report_honestly(self):
        good = harness.run_tests(build_arm(self.root / "good"),
                                 self.task["dir"] / harness.HIDDEN)
        bad = harness.run_tests(build_arm(self.root / "bad", BAD_ARM),
                                self.task["dir"] / harness.HIDDEN)
        self.assertTrue(good["ok"])
        self.assertEqual(good["ran"], 1)
        self.assertFalse(bad["ok"])
        self.assertIn("FAILED", bad["output"])

    def test_packet_carries_no_arm_identity(self):
        arms = [build_arm(self.root / "arm-a"), build_arm(self.root / "arm-b", BAD_ARM)]
        key = harness.build_packet(self.task, arms, self.root / "runs")
        packet = Path(key["packet"])
        blob = "".join(p.read_text(encoding="utf-8") + p.name
                       for p in harness.iter_files(packet))
        self.assertNotIn("arm-a", blob)
        self.assertNotIn("arm-b", blob)
        self.assertEqual(sorted(key["order"]), list(harness.SUBMISSIONS))
        self.assertTrue((packet / "scorecard.md").is_file())

    def test_valid_scorecard_parses(self):
        card = harness.parse_scorecard(FILLED_CARD)
        self.assertEqual(card["winner"], "submission-2")
        self.assertEqual(card["scores"], {"submission-1": 4, "submission-2": 9})
        self.assertTrue(card["graft_reviewed"])
        self.assertEqual(card["judge"], "a human")

    def test_malformed_scorecards_are_refused(self):
        broken = {
            "missing section": FILLED_CARD.replace("## submission-2", "## other"),
            "score out of range": FILLED_CARD.replace("Score: 9", "Score: 11"),
            "score not a number": FILLED_CARD.replace("Score: 9", "Score: great"),
            "winner not a submission": FILLED_CARD.replace("Winner: submission-2", "Winner: arm-a"),
            "graft notes unfilled": FILLED_CARD.replace("Graft notes: nothing worth taking",
                                                        "Graft notes: <what the loser does better>"),
        }
        for label, text in broken.items():
            with self.subTest(label):
                with self.assertRaises(ValueError):
                    harness.parse_scorecard(text)

    def test_each_leg_can_fail_on_its_own(self):
        reds = [
            ("visible tests failing", "visible tests",
             ledger_with(arm={"visible": {"ok": False, "ran": 3}})),
            ("hidden tests failing", "hidden tests",
             ledger_with(arm={"hidden": {"ok": False, "ran": 2}})),
            ("arm holds the hidden tests", "hidden tests",
             ledger_with(arm={"blindness": {"clean": False, "leaks": ["solution.py matches"]}})),
            ("judge picked the other arm, below floor", "blind judge",
             ledger_with(scorecard=dict(ledger_with()["scorecard"], winner="submission-1",
                                        scores={"submission-1": 9, "submission-2": 5}))),
            ("graft not reviewed", "graft review",
             ledger_with(scorecard=dict(ledger_with()["scorecard"], graft_reviewed=False))),
        ]
        for label, leg, ledger in reds:
            with self.subTest(label):
                legs = harness.ship_legs(ledger, "arm-a", 8)
                self.assertEqual([name for name, green, _ in legs if not green], [leg])
        self.assertTrue(all(green for _, green, _ in harness.ship_legs(ledger_with(), "arm-a", 8)))

    def test_a_missing_arm_is_all_four_legs_red(self):
        # ship_legs on an arm id the ledger has never seen (no check, grade,
        # pack, or record run against it) - the "never run" branch of every
        # leg, not just one of them going red.
        empty_ledger = {"task": "t", "arms": {}, "packet": None, "scorecard": None}
        legs = harness.ship_legs(empty_ledger, "never-touched", 8)
        self.assertEqual(
            [name for name, _, _ in legs],
            ["visible tests", "hidden tests", "blind judge", "graft review"],
        )
        self.assertFalse(any(green for _, green, _ in legs))
        details = {name: detail for name, _, detail in legs}
        self.assertIn("never run (eval.py check)", details["visible tests"])
        self.assertIn("never run (eval.py grade)", details["hidden tests"])
        self.assertIn("no scorecard filed", details["blind judge"])
        self.assertIn("not recorded", details["graft review"])

    def test_a_judge_tie_the_loser_still_clears_the_floor(self):
        # Winning isn't the only way the blind-judge leg goes green: an arm
        # that was not picked but still scored at or above the floor is a
        # tie in practice, not a loss, and ship_legs must say so rather than
        # reading "not winner" as automatically red.
        tied = ledger_with(scorecard=dict(
            ledger_with()["scorecard"],
            winner="submission-1",
            scores={"submission-1": 8, "submission-2": 8},
        ))
        legs = harness.ship_legs(tied, "arm-a", 8)
        judge_leg = next(leg for leg in legs if leg[0] == "blind judge")
        self.assertTrue(judge_leg[1], judge_leg)
        self.assertIn("not picked as submission-2, score 8/10 (floor 8)", judge_leg[2])


if __name__ == "__main__":
    unittest.main()
